# -*- coding: utf-8 -*-
"""
Created on Mon Jul 10 15:24:34 2017

@author: a001985
"""
import numpy as np
import pandas as pd
import warnings
import random
import time
import datetime as dt
import os

import core


###############################################################################
def timer(func):
    """
    Created     20180719    by Magnus Wenzer
        
    """

    def f(*args, **kwargs):
        from_time = time.time()
        rv = func(*args, **kwargs)
        to_time = time.time()
        print('"{.__name__}". Time for running method was {}'.format(func, to_time - from_time))
        return rv

    return f


###############################################################################
class IndicatorBase(object):
    """
    Class to calculate status for a specific indicator. 
    """

    def __init__(self, subset_uuid, parent_workspace_object, indicator):
        """
        setup indicator class attributes based on subset, parent workspace object and indicator name

        """
        self.name = indicator.lower()
        print('****INITIATING INDICATOR OBJECT FOR****')
        print(self.name)
        self.class_result = None
        self.subset = subset_uuid
        self.step = 'step_3'
        # from workspace
        self.parent_workspace_object = parent_workspace_object
        # TODO: mapping_objects holds objects with information about:
        # - municipalities, waterdistrikt, type areas etc for each waterbody - information from latest SVAR
        # - hypsography for each waterbody
        # - structure of quality elements (parameters connected to quality elements)
        self.mapping_objects = self.parent_workspace_object.mapping_objects
        # TODO: the index handler contains information used to with get_filtered_data.
        #  So if we instead send data as one of the arguments to this class this should be superfluous
        self.index_handler = self.parent_workspace_object.index_handler
        # TODO: step_object is used to get information about the settings for each indicator/parameter and to get directory to save results in.
        # the textfiles that contains these settings are located in workspaces/your_workspace/subsets/your_subset/step_2/settings/indicator_settings
        self.step_object = self.parent_workspace_object.get_step_object(step=3, subset=self.subset)
        # TODO: subset object seems to not be used in this class.
        self.subset_object = self.parent_workspace_object.get_subset_object(subset=self.subset)

        self.wb_id_header = self.parent_workspace_object.wb_id_header
        # from SettingsFile class
        # TODO: this is now accessed via workspace object, should be sent in via config arg. Settings now read and changed via objects in settings.py
        self.tolerance_settings = self.parent_workspace_object.get_step_object(step=2,
                                                                               subset=self.subset).get_indicator_tolerance_settings(
            self.name)
        self.ref_settings = self.parent_workspace_object.get_step_object(step=2,
                                                                         subset=self.subset).get_indicator_ref_settings(
            self.name)
        # To be read from config-file
        # TODO: Add 'ALABO' and 'TEMP'
        self.meta_columns = ['SDATE', 'YEAR', 'MONTH', 'STATN', 'LATIT_DD', 'LONGI_DD', self.wb_id_header,
                             'WATER_BODY_NAME', 'WATER_DISTRICT_NAME', 'WATER_TYPE_AREA', 'VISS_EU_CD']
        self.meta_columns_shark = ['STIME', 'POSITION', 'WADEP', 'SAMPLE_ID']
        # TODO: the config for which parameters are used for each quality element is not in file Quality_Elements.cfg (a textfile) under resources.
        #  I want to have this in a config file and not hardcoded because it is something that I want to be able to change easily when testing new paremeters or quality elements.
        self.parameter_list = [item.strip() for item in
                               self.mapping_objects['quality_element'].indicator_config.loc[self.name][
                                   'parameters'].split(
                                   ', ')]  # [item.strip() for item in self.parent_workspace_object.cfg['indicators'].loc[self.name][0].split(', ')]
        self.additional_parameter_list = []
        if type(self.mapping_objects['quality_element'].indicator_config.loc[self.name][
                    'additional_parameters']) is str:
            self.additional_parameter_list = [item.strip() for item in
                                              self.mapping_objects['quality_element'].indicator_config.loc[self.name][
                                                  'additional_parameters'].split(
                                                  ', ')]  # [item.strip() for item in self.parent_workspace_object.cfg['indicators'].loc[self.name][0].split(', ')]
        else:
            self.additional_parameter_list = []
        # TODO: information from the config file for quality elements about if status gets better when the value of the parameter increases or decreases
        self.direction_good = self.mapping_objects['quality_element'].indicator_config.loc[self.name]['direction_good']
        # TODO: This now works for sharkdata, but when I run modeldata or satellite data I need to change this since they do not have the meta_columns_shark
        self.column_list = self.meta_columns + self.parameter_list + self.additional_parameter_list + self.meta_columns_shark
        if len(self.column_list) != len(set(self.column_list)):
            raise Exception('Duplicates in self.column_list, check and remove!')
        # print(self.column_list)
        self.indicator_parameter = self.parameter_list[0]
        # attributes that will be calculated
        # TODO: There is a method (_set_water_body_indicator_df) that creates this dataframe by first getting a dataframe using .get_filtered_data() this is called last in the init of each subclass.
        #  It needs information about the name of the parameters to use and some more things that should prabably be in config.
        #  I would like to discuss how much of this we could/should do outside this class
        self.water_body_indicator_df = {}
        #        self.classification_results = ClassificationResult()
        # perform checks before continuing
        self._check()
        self._set_directories()
        # paths and saving
        self.result_directory = self.step_object.paths['step_directory'] + '/output/results/'
        self.sld = core.SaveLoadDelete(self.result_directory)

    def _check(self):

        try:
            variable = self.tolerance_settings.allowed_variables[0]
            self.tolerance_settings.get_value(variable=variable, type_area='1s')
        except AttributeError as e:
            raise AttributeError('Tolerance settings for indicator {} not in place. \n{}'.format(self.name, e))
        try:
            variable = self.ref_settings.allowed_variables[0]
            self.ref_settings.get_value(variable=variable, type_area='1s')
        except AttributeError as e:
            raise AttributeError('Reference value settings for indicator {} not in place. \n{}'.format(self.name, e))

    # ==========================================================================
    def _set_directories(self):
        # set paths
        self.paths = {}
        self.paths['output'] = self.step_object.paths['directory_paths']['output']
        self.paths['results'] = self.step_object.paths['directory_paths']['results']

    # ==========================================================================
    def _add_wb_name_to_df(self, df, water_body):

        try:
            df['WATER_BODY_NAME'] = self.mapping_objects['water_body'][water_body]['WATERBODY_NAME']
        except AttributeError:
            df['WATER_BODY_NAME'] = 'unknown'
            print('waterbody matching file does not recognise water body with {} {}'.format(self.wb_id_header, water_body))

    def _add_type_name_to_df(self, df, water_body):

        try:
            df['WATER_TYPE_AREA'] = self.mapping_objects['water_body'][water_body]['TYPE_AREA_NAME']
        except AttributeError:
            df['WATER_TYPE_AREA'] = 'unknown'
            print('waterbody matching file does not recognise water body with {} {}'.format(self.wb_id_header, water_body))

    def _add_waterdistrict_to_df(self, df, water_body):

        try:
            df['WATER_DISTRICT_NAME'] = self.mapping_objects['water_body'][water_body]['WATER_DISTRICT_NAME']
        except AttributeError:
            df['WATER_DISTRICT_NAME'] = 'unknown'
            print('waterbody matching file does not recognise water body with {} {}'.format(self.wb_id_header, water_body))

    # ==========================================================================
    def _add_reference_value_to_df(self, df, water_body):
        """
        Created:        20180426     by Lena
        Last modified:  
        add reference value to dataframe
        Nutrient reference values: Det aktuella referensvärdet erhålls utifrån den salthalt som är observerad vidvarje enskilt prov.
        Chl, Biov, Secchi in type 8, 12, 13, 24: Det aktuella referensvärdet erhålls utifrån den salthalt som är observerad vidvarje enskilt prov.
        """
        # print(water_body,len(self.ref_settings.settings.refvalue_column))
        if len(self.ref_settings.settings.refvalue_column) == 0:
            return df

        # print(self.get_ref_value_type(water_body = water_body))
        if self.get_ref_value_type(water_body=water_body) == 'str':
            reference_values = []
            for ix in df.index:
                salinity = df[self.salt_parameter][ix]
                #                #print(repr(salinity))
                #                #if np.isnan(salinity):
                #                #    df['REFERENCE_VALUE'].loc[ix] = np.nan
                #                #else:
                reference_values.append(self.get_boundarie(water_body=water_body, salinity=salinity))
            #                df['REFERENCE_VALUE'].loc[ix] = self.get_ref_value(water_body = water_body, salinity = salinity)
            #            df['REFERENCE_VALUE'] = reference_values
            df.loc[:, 'REFERENCE_VALUE'] = pd.Series(reference_values, index=df.index)
        else:
            df.loc[:, 'REFERENCE_VALUE'] = self.get_ref_value(water_body)

        return df

    # ==========================================================================
    def _add_boundaries_to_df(self, df, water_body):
        """
        Created:        20180426     by Lena
        Last modified:  
        add reference value to dataframe
        Nutrient reference values: Det aktuella referensvärdet erhålls utifrån den salthalt som är observerad vidvarje enskilt prov.
        Chl, Biov, Secchi in type 8, 12, 13, 24: Det aktuella referensvärdet erhålls utifrån den salthalt som är observerad vidvarje enskilt prov.
        """
        #         print('add_boundaries')
        # print(water_body,len(self.ref_settings.settings.refvalue_column))
        if len(self.ref_settings.settings.refvalue_column) == 0:
            return df

        HG_EQR_LIMIT = self.ref_settings.get_value(variable='HG_EQR_LIMIT', water_body=water_body)
        GM_EQR_LIMIT = self.ref_settings.get_value(variable='GM_EQR_LIMIT', water_body=water_body)
        MP_EQR_LIMIT = self.ref_settings.get_value(variable='MP_EQR_LIMIT', water_body=water_body)
        PB_EQR_LIMIT = self.ref_settings.get_value(variable='PB_EQR_LIMIT', water_body=water_body)

        # print(self.get_ref_value_type(water_body = water_body))
        if self.get_ref_value_type(water_body=water_body) == 'str':
            salt_values = df.loc[:, self.salt_parameter].copy().values
            ref_list = self.get_ref_value(water_body=water_body, salinity=salt_values)
            df.loc[:, 'REFERENCE_VALUE'] = ref_list
            # TODO: should not enter here if ref value is not an equations
            if not isinstance(ref_list, list):
                ref_list = [ref_list]

            if self.direction_good == 'positive':
                df.loc[:, 'HG_VALUE_LIMIT'] = [item * HG_EQR_LIMIT for item in ref_list]
                df.loc[:, 'GM_VALUE_LIMIT'] = [item * GM_EQR_LIMIT for item in ref_list]
                df.loc[:, 'MP_VALUE_LIMIT'] = [item * MP_EQR_LIMIT for item in ref_list]
                df.loc[:, 'PB_VALUE_LIMIT'] = [item * PB_EQR_LIMIT for item in ref_list]
            elif self.direction_good == 'negative':
                df.loc[:, 'HG_VALUE_LIMIT'] = [item / HG_EQR_LIMIT for item in ref_list]
                df.loc[:, 'GM_VALUE_LIMIT'] = [item / GM_EQR_LIMIT for item in ref_list]
                df.loc[:, 'MP_VALUE_LIMIT'] = [item / MP_EQR_LIMIT for item in ref_list]
                df.loc[:, 'PB_VALUE_LIMIT'] = [item / PB_EQR_LIMIT for item in ref_list]
            # print('ref_value is str')
        else:
            ref_value = self.get_ref_value(water_body=water_body, variable='REF_VALUE_LIMIT')
            df.loc[:, 'REFERENCE_VALUE'] = ref_value
            if self.direction_good == 'positive':
                df.loc[:, 'HG_VALUE_LIMIT'] = ref_value * HG_EQR_LIMIT
                df.loc[:, 'GM_VALUE_LIMIT'] = ref_value * GM_EQR_LIMIT
                df.loc[:, 'MP_VALUE_LIMIT'] = ref_value * MP_EQR_LIMIT
                df.loc[:, 'PB_VALUE_LIMIT'] = ref_value * PB_EQR_LIMIT
            elif self.direction_good == 'negative':
                df.loc[:, 'HG_VALUE_LIMIT'] = ref_value / HG_EQR_LIMIT
                df.loc[:, 'GM_VALUE_LIMIT'] = ref_value / GM_EQR_LIMIT
                df.loc[:, 'MP_VALUE_LIMIT'] = ref_value / MP_EQR_LIMIT
                df.loc[:, 'PB_VALUE_LIMIT'] = ref_value / PB_EQR_LIMIT

    #        return df

    # ==========================================================================
    def _calculate_global_EQR_from_indicator_value(self, water_body=None, value=None, max_value=None, min_value=0,
                                                   **kwargs):
        """
        Calculates EQR from local_EQR values according to eq. 1 in WATERS final report p 153.
        Boundaries for all classes are read from RefSettings object
        boundarie_variable is used to retrieve class boundaries from settings file and must match the type of value
        This is only valid for values with increasing quality (higher value = higher EQR)
        """
        if not value:
            return False, False

        if np.isnan(value):
            global_EQR = np.nan
            status = ' '
            return global_EQR, status

        if value < 0:
            if self.name == 'indicator_oxygen':
                value = 1e-10
            else:
                raise ('Error: _calculate_global_EQR_from_indicator_value: {} value below 0.'.format(value))

        # Get EQR-class limits for the type area to be able to calculate the weighted numerical class
        def select_source(kwargs, key):
            if key in kwargs.keys():
                return kwargs[key]
            else:
                return self.ref_settings.get_value(variable=key, water_body=water_body)

        if 'REF_VALUE_LIMIT' in kwargs.keys():
            REF_VALUE = kwargs['REF_VALUE_LIMIT']
        else:
            REF_VALUE = self.ref_settings.get_ref_value(water_body=water_body)

        HG_VALUE_LIMIT = select_source(kwargs, 'HG_VALUE_LIMIT')
        GM_VALUE_LIMIT = select_source(kwargs, 'GM_VALUE_LIMIT')
        MP_VALUE_LIMIT = select_source(kwargs, 'MP_VALUE_LIMIT')
        PB_VALUE_LIMIT = select_source(kwargs, 'PB_VALUE_LIMIT')

        #        HG_VALUE_LIMIT = self.ref_settings.get_value(variable = 'HG_VALUE_LIMIT', water_body = water_body)
        #        GM_VALUE_LIMIT = self.ref_settings.get_value(variable = 'GM_VALUE_LIMIT', water_body = water_body)
        #        MP_VALUE_LIMIT = self.ref_settings.get_value(variable = 'MP_VALUE_LIMIT', water_body = water_body)
        #        PB_VALUE_LIMIT = self.ref_settings.get_value(variable = 'PB_VALUE_LIMIT', water_body = water_body)
        if not max_value:
            max_value = REF_VALUE

        #        if self.name == 'BQI'  or self.name.lower() == 'oxygen':
        if HG_VALUE_LIMIT - GM_VALUE_LIMIT > 0:
            slope = 0.2
            # When lower value means lower status (decreasing)
            if value > HG_VALUE_LIMIT:
                status = 'HIGH'
                global_low = 0.8
                high_value = max_value  # REF_VALUE #This should be the highest value possible
                low_value = HG_VALUE_LIMIT

            elif value > GM_VALUE_LIMIT:
                status = 'GOOD'
                global_low = 0.6
                high_value = HG_VALUE_LIMIT
                low_value = GM_VALUE_LIMIT

            elif value > MP_VALUE_LIMIT:
                status = 'MODERATE'
                global_low = 0.4
                high_value = GM_VALUE_LIMIT
                low_value = MP_VALUE_LIMIT

            elif value > PB_VALUE_LIMIT:
                status = 'POOR'
                global_low = 0.2
                high_value = MP_VALUE_LIMIT
                low_value = PB_VALUE_LIMIT

            else:
                status = 'BAD'
                global_low = 0
                high_value = PB_VALUE_LIMIT
                low_value = 0

        else:
            slope = -0.2
            # When higher value means lower status (decreasing)
            if value > PB_VALUE_LIMIT:
                status = 'BAD'
                global_low = 0.2
                high_value = 1
                # om värde ist för ek ska ek_high vara ref_värdet eller Bmax värde
                low_value = PB_VALUE_LIMIT
                if value > max_value:
                    value = max_value

            elif value > MP_VALUE_LIMIT:
                status = 'POOR'
                global_low = 0.4
                high_value = PB_VALUE_LIMIT
                low_value = MP_VALUE_LIMIT

            elif value > GM_VALUE_LIMIT:
                status = 'MODERATE'
                global_low = 0.6
                high_value = MP_VALUE_LIMIT
                low_value = GM_VALUE_LIMIT

            elif value > HG_VALUE_LIMIT:
                status = 'GOOD'
                global_low = 0.8
                high_value = GM_VALUE_LIMIT
                low_value = HG_VALUE_LIMIT

            else:
                status = 'HIGH'
                global_low = 1
                high_value = HG_VALUE_LIMIT
                low_value = 0
                if value < 0:
                    value = 1e-10
            # global_EQR = global_low + (ek - ek_low)/(ek_high-ek_low)*-0.2

        #        print('******',REF_VALUE,'******')
        #        print('-------', HG_VALUE_LIMIT - GM_VALUE_LIMIT , '-------')
        #        print(global_low, value, low_value, high_value)
        # Weighted numerical class
        global_EQR = global_low + (value - low_value) / (high_value - low_value) * slope

        return global_EQR, status

    # ==========================================================================
    def _calculate_global_EQR_from_local_EQR(self, local_EQR, water_body):
        """
        Calculates EQR from local_EQR values according to eq. 1 in WATERS final report p 153.
        Boundaries for all classes are read from RefSettings object
        boundarie_variable is used to retrieve class boundaries from settings file and must match the type of local_EQR_variable
        """

        if np.isnan(local_EQR):
            global_EQR = np.nan
            status = ''
            return global_EQR, status
        if local_EQR < 0:
            raise Exception(
                'Error: _calculate_global_EQR_from_local_EQR: {} local_EQR value below 0.'.format(local_EQR))

        # Get EQR-class limits for the type area to be able to calculate the weighted numerical class
        HG_EQR_LIMIT = self.ref_settings.get_value(variable='HG_EQR_LIMIT', water_body=water_body)
        GM_EQR_LIMIT = self.ref_settings.get_value(variable='GM_EQR_LIMIT', water_body=water_body)
        MP_EQR_LIMIT = self.ref_settings.get_value(variable='MP_EQR_LIMIT', water_body=water_body)
        PB_EQR_LIMIT = self.ref_settings.get_value(variable='PB_EQR_LIMIT', water_body=water_body)

        ek = local_EQR
        #        if self.name == 'BQI' or self.name.lower() == 'secchi' or self.name.lower() == 'oxygen':
        #            return False
        #        else:
        if HG_EQR_LIMIT - GM_EQR_LIMIT > 0:
            # When higher EQR means higher status (increasing)
            if ek > HG_EQR_LIMIT:
                status = 'HIGH'
                global_low = 0.8
                ek_high = 1
                # om värde ist för ek ska ek_high vara ref_värdet eller Bmax värde
                ek_low = HG_EQR_LIMIT
                if ek > 1:
                    ek = 1

            elif ek > GM_EQR_LIMIT:
                status = 'GOOD'
                global_low = 0.6
                ek_high = HG_EQR_LIMIT
                ek_low = GM_EQR_LIMIT

            elif ek > MP_EQR_LIMIT:
                status = 'MODERATE'
                global_low = 0.4
                ek_high = GM_EQR_LIMIT
                ek_low = MP_EQR_LIMIT

            elif ek > PB_EQR_LIMIT:
                status = 'POOR'
                global_low = 0.2
                ek_high = MP_EQR_LIMIT
                ek_low = PB_EQR_LIMIT

            else:
                status = 'BAD'
                global_low = 0
                ek_high = PB_EQR_LIMIT
                ek_low = 0
                if ek < 0:
                    ek = 0

        else:
            # When higher EQR means lower status (decreasing)
            if ek > PB_EQR_LIMIT:
                status = 'BAD'
                global_low = 0.2
                ek_high = 1
                # om värde ist för ek ska ek_high vara ref_värdet eller Bmax värde
                ek_low = PB_EQR_LIMIT
                if ek > 1:
                    ek = 1

            elif ek > MP_EQR_LIMIT:
                status = 'POOR'
                global_low = 0.4
                ek_high = PB_EQR_LIMIT
                ek_low = MP_EQR_LIMIT

            elif ek > GM_EQR_LIMIT:
                status = 'MODERATE'
                global_low = 0.6
                ek_high = MP_EQR_LIMIT
                ek_low = GM_EQR_LIMIT

            elif ek > HG_EQR_LIMIT:
                status = 'GOOD'
                global_low = 0.8
                ek_high = GM_EQR_LIMIT
                ek_low = HG_EQR_LIMIT

            else:
                status = 'HIGH'
                global_low = 1
                ek_high = HG_EQR_LIMIT
                ek_low = 0
                # should this not be 1?
                if ek < 0:
                    ek = 0

        # Weighted numerical class
        global_EQR = global_low + (ek - ek_low) / (ek_high - ek_low) * 0.2
        return global_EQR, status


    @timer
    # ==========================================================================
    def _set_water_body_indicator_df(self, water_body=None):
        """
        Created:        20180215     by Lena
        Last modified:  20180328     by Lena
        df should contain:
            - all needed columns from get_filtered_data
            - referencevalues
            - maybe other info needed for indicator functions
        skapa df utifrån:
        self.index_handler
        self.tolerance_settings
        self.indicator_ref_settings
        """

        # type_area = self.mapping_objects['water_body'].get_type_area_for_water_body(water_body, include_suffix=True)
        if water_body:
            filtered_data = self.get_filtered_data(subset=self.subset, step='step_2', water_body=water_body,
                                                   indicator=self.name).dropna(subset=[self.indicator_parameter])
            if len(filtered_data) == 0:
                #            if water_body not in filtered_data.VISS_EU_CD.unique():
                print('no data for waterbody {}'.format(water_body))
                return False
            water_body_list = [water_body]

        else:
            water_body_list = self.get_filtered_data(subset=self.subset, step='step_2').dropna(
                subset=[self.indicator_parameter], how='all')[self.wb_id_header].unique()
        # TODO: if waterbody with only stations from adjecent waterbody, how do I include it?
        water_body_list = self.get_filtered_data(subset=self.subset, step='step_2')[self.wb_id_header].unique().tolist()
        # waterbodies in the include and exclude station filters in step_2/settings/water_body
        # add_wb = [file[11:-4] for file in os.listdir(self.subset_object.paths['subset_directory']+'/step_2/settings/water_body/')]
        # [water_body_list.append(wb) for wb in add_wb if wb not in water_body_list]

        for water_body in dict.fromkeys(water_body_list, True):
            try:
                filtered_data = self.get_filtered_data(subset=self.subset, step='step_2',
                                       water_body=water_body, indicator=self.name)[self.column_list].copy()
            except core.exceptions.BooleanNotFound:
                print('No boolean found for waterbody {}'.format(water_body))
                continue

            if filtered_data.empty:
                self.water_body_indicator_df[water_body] = filtered_data.copy()
                continue
            try:
                self.mapping_objects['water_body'][water_body]['WATERBODY_NAME']
            except AttributeError:
                self.water_body_indicator_df[water_body] = filtered_data.copy()
                continue
            if (len(filtered_data[self.wb_id_header].unique()) > 1) or (filtered_data[self.wb_id_header].unique() != water_body):
                print('Warning: get_filtered_data() returns {} waterbody. Input waterbody is {}'.format(
                    filtered_data[self.wb_id_header].unique(), water_body))
                # raise Exception('Error: get_filtered_data() returns {} waterbody. Input waterbody is {}'.format(df[self.wb_id_header].unique(), water_body))
                # df = filtered_data.iloc[0:0]
                # self.water_body_indicator_df[water_body]
            if self.name == 'indicator_chl':
                type_area = self.mapping_objects['water_body'].get_type_area_for_water_body(water_body,
                                                                                            include_suffix=False)
                boolean = ((filtered_data.MXDEP <= self.end_deph_max) & (
                            filtered_data.MNDEP <= self.start_deph_max)) | (~filtered_data.DEPH.isnull())
                #if type_area in self.notintegrate_typeareas:
                #    df = filtered_data.loc[boolean].dropna(subset=['CPHL_BTL']).copy()
                #                     df = df[df['DEPH'].isin(df.groupby(['SDATE', 'YEAR', 'STATN']).min()['DEPH'].values)]
                #                 if self.parameter_list[0] in filtered_data.columns and self.parameter_list[1] in filtered_data.columns:
                #else:
                # 20190123: removed if-statement above since finding surface value is done in calculating status.
                df = filtered_data.loc[boolean].dropna(subset=self.indicator_parameter, how='all').copy()
            elif self.name == 'indicator_biov':
                df = filtered_data.loc[
                    (filtered_data.MXDEP <= self.end_deph_max) & (filtered_data.MNDEP <= self.start_deph_max)].dropna(
                    subset=[self.indicator_parameter]).copy()
            elif self.name == 'indicator_secchi':
                df = filtered_data.dropna(subset=[self.indicator_parameter]).drop_duplicates(
                    subset=['SDATE', self.wb_id_header, 'STATN', self.indicator_parameter]).copy()
            #             elif self.name == 'indicator_oxygen':
            #                 df = filtered_data.dropna(subset = [self.indicator_parameter]).copy()
            #                 tol_BW = 5
            #                 maxD = self.Hypsographs.get_max_depth_of_water_body(water_body)
            #                 if maxD:
            #                     self.df_bottomwater[water_body] = df.loc[df['DEPH'] > maxD-self.tol_BW].copy()
            #                 else:
            #                     self.df_bottomwater[water_body] = df.copy()
            #                self.df_bottomwater[water_body] = df.loc[df['DEPH'] > maxD-tol_BW]
            else:
                df = filtered_data.dropna(subset=[self.indicator_parameter]).copy()
            if df.empty:
                self.water_body_indicator_df[water_body] = df
                continue
            #            if hasattr(self, 'salt_parameter'):
            if self.name not in ['indicator_oxygen', 'indicator_biov', 'indicator_chl']:
                #                 print('this is where the SettingCopyWithWarning is raised!!!')
                self._add_boundaries_to_df(df, water_body)
            self.water_body_indicator_df[water_body] = df

            # ==========================================================================

    def float_convert(self, x):
        try:
            return float(x)
        except:
            return np.nan

            # ==========================================================================

    def get_closest_matching_salinity(self, sdate, statn, waterbody, deph_max=999, deph_min=0, dayspan = 1):
        """
        get closest matching salinity value when salinity is missing. 
        TODO: use tolerance info from settings file
        """
        try:
            date = dt.datetime.strptime(sdate, "%Y-%m-%d")
        except ValueError as e:
            raise EkostatInternalException(message=e.message)
        date_max = date + dt.timedelta(days=dayspan)
        date_min = date - dt.timedelta(days=dayspan)
        df = self.get_filtered_data(step='step_1', subset=self.subset).copy()
        try:
            datetimeseries = pd.to_datetime(df.SDATE)
        except ValueError as e:
            raise EkostatInternalException(message=e.message)
        s = df.loc[(datetimeseries <= date_max) & (datetimeseries >= date_min) &
                   (df.STATN == statn) & (df[self.wb_id_header] == waterbody) & (df.DEPH >= deph_min) &
                   (df.DEPH <= deph_max), 'SALT']
        if len(s) > 0:
            if len(s) > 1:
                #print('salinity from closest matching: \t {}'.format(np.mean(s)))
                return np.mean(s)
            else:
                #print('salinity from closest matching: \t {}'.format(s.values[0]))
                return s.values[0]
        else:
            #print('no salinity within {} days from {} at {}'.format(dayspan, date, statn))
            return np.nan

    # ==========================================================================
    def get_filtered_data(self, subset=None, step=None, water_body=None, indicator=None):
        """
        Filter for water_body and indicator means filters from indicator_settings are applied.
        But the filters are only applied if they first are added to the index_handler so need to check if water_body and indicator have filters added
        """

        return self.index_handler.get_filtered_data(subset, step, water_body, indicator)

    #    #==========================================================================
    #    def get_numerical_class(self, ek, water_body):
    #        """
    #        Calculates indicator class (Nklass) according to eq 2.1 in HVMFS 2013:19.
    #        Returns a tuple with four values, low, ek_low, ek_heigh and the resulting Nklass.
    #        This is specific for the nutrient and phytoplankton indicators.
    #        There needs to be:
    #            - one def to get nutrient num_class for nutrient indicators (this one as is)
    #            - one def to get indicator class and value with the indicator specific EQR and the EQR transformed to the common scale
    #            (for nutrients that is num_class on scale 0-4.99 for most others some values on a 0-1 scale)
    #        """
    #        type_area = self.mapping_objects['water_body'].get_type_area_for_water_body(water_body, include_suffix=True)
    #        # Get EQR-class limits for the type area to be able to calculate the weighted numerical class
    #        HG_EQR_LIMIT = self.ref_settings.get_value(variable = 'HG_EQR_LIMIT', type_area = type_area)
    #        GM_EQR_LIMIT = self.ref_settings.get_value(variable = 'GM_EQR_LIMIT', type_area = type_area)
    #        MP_EQR_LIMIT = self.ref_settings.get_value(variable = 'MP_EQR_LIMIT', type_area = type_area)
    #        PB_EQR_LIMIT = self.ref_settings.get_value(variable = 'PB_EQR_LIMIT', type_area = type_area)
    #
    #        if self.name == 'BQI' or self.name.lower() == 'secchi' or self.name.lower() == 'oxygen':
    #            return False
    #        else:
    #            if ek > HG_EQR_LIMIT:
    #                status = 'HIGH'
    #                n_low = 4
    #                ek_high = 1
    #                ek_low = HG_EQR_LIMIT
    #
    #            elif ek > GM_EQR_LIMIT:
    #                status = 'GOOD'
    #                n_low = 3
    #                ek_high = HG_EQR_LIMIT
    #                ek_low = GM_EQR_LIMIT
    #
    #            elif ek > MP_EQR_LIMIT:
    #                status = 'MODERATE'
    #                n_low = 2
    #                ek_high = GM_EQR_LIMIT
    #                ek_low = MP_EQR_LIMIT
    #
    #            elif ek > PB_EQR_LIMIT:
    #                status = 'POOR'
    #                n_low = 1
    #                ek_high = MP_EQR_LIMIT
    #                ek_low = PB_EQR_LIMIT
    #
    #            else:
    #                status = 'BAD'
    #                n_low = 0
    #                ek_high = PB_EQR_LIMIT
    #                ek_low = 0
    #
    #            # Weighted numerical class
    #            n_class = n_low + (ek - ek_low)/(ek_high-ek_low)
    #
    #            return n_low, ek_low, ek_high, status, n_class
    #

    # ==========================================================================
    def get_ref_value_type(self, type_area=None, water_body=None):
        """
        Created:        20180328     by Lena
        Last modified:  
        Get referencevalue either from equation or directly from settings
        To get reference value from equation you need to supply both type_area and salinity
        """
        return self.ref_settings.get_ref_value_type(type_area=type_area, water_body=water_body)

    # ==========================================================================
    def get_ref_value(self, type_area=None, water_body=None, salinity=None, variable=None):
        """
        Created:        20181013     by Lena
        Last modified:  
        Get referencevalue either from equation or directly from settings
        To get reference value from equation you need to supply both type_area and salinity
        
        """
        return self.ref_settings.get_ref_value(type_area=type_area, water_body=water_body, salinity=salinity)

    # ==========================================================================
    def get_boundarie(self, type_area=None, water_body=None, salinity=None, variable=None):
        """
        Created:        20180328     by Lena
        Last modified:  
        Get referencevalue either from equation or directly from settings
        To get reference value from equation you need to supply both type_area and salinity
        
        """
        return self.ref_settings.get_boundarie(type_area=type_area, water_body=water_body, salinity=salinity,
                                               variable=variable)

    # ==========================================================================
    def get_water_body_indicator_df(self, water_body=None):
        """
        Created:        20180215     by Lena
        Last modified:  20180720     by Magnus
        df should contains:
            - all needed columns from get_filtered_data
            - referencevalues
        TODO: add other info needed for indicator functions
        """

        return self.water_body_indicator_df.get(water_body, False)

    #        return self.water_body_indicator_df[water_body]

    # ==========================================================================
    def get_status_from_global_EQR(self, global_EQR):

        if global_EQR >= 0.8:
            return 'HIGH'
        elif global_EQR >= 0.6:
            return 'GOOD'
        elif global_EQR >= 0.4:
            return 'MODERATE'
        elif global_EQR >= 0.2:
            return 'POOR'
        elif global_EQR >= 0:
            return 'BAD'
        else:
            return ''


#    #==========================================================================
#    def get_ref_value_for_par_with_salt_ref(self, par=None, salt_par='SALT_CTD', indicator_name=None, tolerance_filter=None):
#        """
#        tolerance_filters is a dict with tolerance filters for the specific (sub) parameter. 
#        """
#        """
#        Vid statusklassificering
#        ska värden från ytvattnet användas (0-10 meter eller den övre vattenmassan
#        om språngskiktet är grundare än 10 meter).
#        
#        Om mätningar vid ett tillfälle är utförda vid diskreta djup, exempelvis 0, 5 och 10
#        meter ska EK-värde beräknas för varje mätning och ett medel–EK skapas för de tre
#        djupen.
#        """
##        class_result = ClassificationResult()
##        class_result.add_info('parameter', par)
##        class_result.add_info('salt_parameter', salt_par)
##        class_result.add_info('type_area', self.data_filter_object.TYPE_AREA.value)
#        
#        """
#        För kvalitetsfaktorn Näringsämnen: 
#        1) Beräkna EK för varje enskilt prov utifrån referensvärden i tabellerna 6.2-6.7.
#        Det aktuella referensvärdet erhålls utifrån den salthalt som är observerad vid
#        varje enskilt prov. Om mätningar är utförda vid diskreta djup, beräkna EKvärde
#        för varje mätning och sedan ett medel-EK för varje specifikt mättillfälle.
#        """
#        
#        ref_object = getattr(core.RefValues(), indicator_name.lower())[self.data_filter_object.TYPE_AREA.value]
##        self.ref_object = ref_object
#        par_object = getattr(self, par.lower())
#        salt_object = getattr(self, salt_par.lower())
#        self.par_object = par_object
#        self.salt_object = salt_object
#        
#        par_df = par_object.data.column_data.copy(deep=True)
#        salt_df = salt_object.data.column_data
#        
#        par_df['salt_value_ori'] = np.nan 
#        par_df['salt_value'] = np.nan 
#        par_df['salt_index'] = np.nan 
#        par_df['ref_value'] = np.nan 
#        #par_df['ek_value_calc'] = np.nan 
#        par_df['par_value'] = np.nan 
#        for i in par_df.index:
##            self.i = i
#            df_row = par_df.loc[i, :]
#            par_value = df_row[par]
#            if np.isnan(par_value):
#                ref_value = np.nan
#            else:
#                try:
#                    salt_df.loc[1, salt_par]
#                    first_salt = 1 
#                except KeyError:
#                    # TODO: Why was default set to 1?
#                    first_salt = salt_df.index[0]
#                if i in salt_df.index and not np.isnan(salt_df.loc[first_salt, salt_par]): 
#                    salt_value_ori = salt_df.loc[first_salt, salt_par]  # ska inte det vara: salt_df.loc[i, salt_par]?
#                    salt_index = i
#                else:
#                    # TODO: If not allowed to continue
#                    matching_salt_data = salt_object.get_closest_matching_data(df_row=df_row, 
#                                                                             tolerance_filter=tolerance_filter)
#                    if matching_salt_data.empty:
#                        salt_value_ori = np.nan
#                        salt_index = np.nan
#                        self.missing = df_row
#                    else:
#                        self.matching_salt_data = matching_salt_data
#                        salt_value_ori = matching_salt_data[salt_par]
#                        salt_index = matching_salt_data.name
#                        
#                # Check salt for maximum value
#                salt_value = ref_object.get_max_salinity(salt_value_ori)
#                
#                # Get ref value
#                ref_value = ref_object.get_ref_value(salt_value)
#                
#                # Get EK-value
#                
#                # TODO: This differs between indicators, some are ref/obs other obs/ref
#                # So this should not be in IndicatorBase, output from this def should be salt_val, ref_val och par_val
##                ek_value_calc = ref_value/par_value
#                
##                self.salt_value = salt_value
##                self.ek_value_calc = ek_value_calc
##                self.ref_value = ref_value
##                self.par_value = par_value
##            print('ref_value', ref_value, '=', value)
##            self.df_row = df_row
##            self.salt_value = salt_value
#            par_df.set_value(i, 'salt_value_ori', salt_value_ori) 
#            par_df.set_value(i, 'salt_value', salt_value) 
#            par_df.set_value(i, 'salt_index', salt_index)
#            par_df.set_value(i, 'ref_value', ref_value)
#            par_df.set_value(i, 'par_value', par_value)
#            
#            # Check ek_value_calc
##            ek_value = ek_value_calc
##            if ek_value > 1:
##                ek_value = 1
##            par_df.set_value(i, 'ek_value', ek_value)
#        return par_df        

###############################################################################
class IndicatorBQI(IndicatorBase):
    """
    Class with methods for BQI indicator. 
    """

    def __init__(self, subset_uuid, parent_workspace_object, indicator):
        super().__init__(subset_uuid, parent_workspace_object, indicator)
        self.indicator_parameter = self.parameter_list[0]
        # self.column_list.remove('DEPH')
        [self.column_list.append(c) for c in ['MNDEP', 'MXDEP', 'SLABO'] if c not in self.column_list]
        # Set dataframe to use        
        self._set_water_body_indicator_df(water_body=None)

    # ==================================================================================================================
    def _add_boundaries_to_df(self, df, water_body):
        # TODO: need to add by STATN, DATE
        self.stations = df.STATN.unique()
        df.loc[:, 'REFERENCE_VALUE'] = pd.Series(np.nan, index=df.index)
        df.loc[:, 'HG_VALUE_LIMIT'] = pd.Series(np.nan, index=df.index)
        df.loc[:, 'GM_VALUE_LIMIT'] = pd.Series(np.nan, index=df.index)
        df.loc[:, 'MP_VALUE_LIMIT'] = pd.Series(np.nan, index=df.index)
        df.loc[:, 'PB_VALUE_LIMIT'] = pd.Series(np.nan, index=df.index)
        #        print(df.head())
        for station in self.stations:
            ix = df.index[df.STATN == station]
            station_values = df.loc[ix]

            mxdep_list = [self.float_convert(p) for p in station_values.MXDEP.unique()]
            mndep_list = [self.float_convert(p) for p in station_values.MNDEP.unique()]
            if np.isnan(mxdep_list).all and np.isnan(mndep_list).all:
                #                print(mxdep_list)
                mxdep_list = [self.float_convert(p) for p in station_values.WADEP.unique()]
                if np.isnan(mxdep_list).all:
                    ref_value = np.nan
                    hg_value = np.nan
                    gm_value = np.nan
                    mp_value = np.nan
                    pb_value = np.nan
            #                print('WADEP used', mxdep_list)
            if np.isnan(mxdep_list).all() and not np.isnan(mndep_list).all():
                mxdep_list = [max(mndep_list)]
            if np.isnan(mndep_list).all():
                mndep_list = [min(mxdep_list)]

            ref_value = self._get_value(water_body=water_body, variable='REF_VALUE_LIMIT', MXDEP_list=mxdep_list,
                                        MNDEP_list=mndep_list)
            #            ref_value, hg_value, gm_value, mp_value, pb_value = self._get_value(water_body = water_body, variable = ['REF_VALUE_LIMIT', 'HG_VALUE_LIMIT', 'GM_VALUE_LIMIT', 'MP_VALUE_LIMIT', 'PB_VALUE_LIMIT'], MXDEP_list = mxdep_list, MNDEP_list = mndep_list)
            #            hg_value = (ref_value*self.ref_settings.get_value(variable = 'HG_EQR_LIMIT', water_body = water_body))
            #            gm_value = (ref_value*self.ref_settings.get_value(variable = 'GM_EQR_LIMIT', water_body = water_body))
            #            mp_value = (ref_value*self.ref_settings.get_value(variable = 'MP_EQR_LIMIT', water_body = water_body))
            #            pb_value = (ref_value*self.ref_settings.get_value(variable = 'PB_EQR_LIMIT', water_body = water_body))

            hg_value = self._get_value(water_body=water_body, variable='HG_VALUE_LIMIT', MXDEP_list=mxdep_list,
                                       MNDEP_list=mndep_list)
            gm_value = self._get_value(water_body=water_body, variable='GM_VALUE_LIMIT', MXDEP_list=mxdep_list,
                                       MNDEP_list=mndep_list)
            mp_value = self._get_value(water_body=water_body, variable='MP_VALUE_LIMIT', MXDEP_list=mxdep_list,
                                       MNDEP_list=mndep_list)
            pb_value = self._get_value(water_body=water_body, variable='PB_VALUE_LIMIT', MXDEP_list=mxdep_list,
                                       MNDEP_list=mndep_list)
            #            if not ref_value:
            #                print('no ref_value', df.WATER_BODY_NAME.unique(), df.WATER_TYPE_AREA.unique(), ref_value)
            df.loc[ix, 'REFERENCE_VALUE'] = pd.Series(ref_value, index=ix)
            df.loc[ix, 'HG_VALUE_LIMIT'] = pd.Series(hg_value, index=ix)
            df.loc[ix, 'GM_VALUE_LIMIT'] = pd.Series(gm_value, index=ix)
            df.loc[ix, 'MP_VALUE_LIMIT'] = pd.Series(mp_value, index=ix)
            df.loc[ix, 'PB_VALUE_LIMIT'] = pd.Series(pb_value, index=ix)

    # ==================================================================================================================
    def _get_deph_interval_list(self, water_body, MXDEP_list, MNDEP_list):

        interval = self.ref_settings.get_value(variable='DEPH_INTERVAL', water_body=water_body)
        if type(interval) is bool and not interval:
            #            print('interval is', interval)
            return False

        deph_interval_list = False
        if type(interval) is tuple:
            # check that position depths are within interval    
            if max(MXDEP_list) <= max(interval) and min(MNDEP_list) >= min(interval):
                deph_interval_list = [str(interval[0]) + '-' + str(interval[1])]
        #        if np.isnan(min(MNDEP_list)):
        #            MNDEP_list = [min(deph_interval_list)]
        else:
            for row in (interval.get_values()):
                #                print('row is ',row)
                interval_list = [int(value) for value in row.split('-')]
                #                print('interval_list is',interval_list)
                #                print('min dep is ',min(MNDEP_list))
                #                print('max dep is ',min(MXDEP_list))
                #                print('check mxdep {} <= {} and mndep {} >= {}'.format(max(MXDEP_list), max(interval_list), min(MNDEP_list),min(interval_list)))
                #                print(MXDEP_list, MNDEP_list)
                if max(MXDEP_list) <= max(interval_list) and min(MNDEP_list) >= min(interval_list):
                    deph_interval_list = [str(interval_list[0]) + '-' + str(interval_list[1])]
                if deph_interval_list:
                    break

        return deph_interval_list

    # ==================================================================================================================
    def _get_settings_index(self, water_body, MXDEP_list, MNDEP_list):

        deph_interval_list = self._get_deph_interval_list(water_body, MXDEP_list, MNDEP_list)
        #        print('deph_interval_list', deph_interval_list)

        if deph_interval_list:
            df = self.ref_settings.get_value(water_body=water_body)
            #            print(df['LEVEL_DEPH_INTERVAL'])
            ix = df.loc[df['DEPH_INTERVAL'] == deph_interval_list[0]].index
            return ix[0]
        else:
            #            interval = self.ref_settings.get_value(variable = 'LEVEL_DEPH_INTERVAL', water_body = water_body)
            #            print('deph_interval_list', deph_interval_list)
            #            print('MXDEP_list {}, MNDEP_list {}'.format(MXDEP_list, MNDEP_list))
            #            print('outside range {}'.format(interval))
            return False

    def _get_value(self, water_body, variable, MXDEP_list, MNDEP_list):

        ix = self._get_settings_index(water_body, MXDEP_list, MNDEP_list)
        if ix:
            if type(variable) is list:
                results = []
                for var in variable:
                    results.append(float(self.ref_settings.get_value(water_body=water_body).loc[ix][var]))
                return tuple(results)
            return float(self.ref_settings.get_value(water_body=water_body).loc[ix][variable])
        else:
            #            print(MXDEP_list, MNDEP_list, self.ref_settings.get_value(water_body = water_body))
            if type(variable) is list:
                return (False,) * len(variable)
            return False

    # ===============================================================
    def calculate_status(self, water_body):
        """
        Calculates indicatotr EQR for BQI values using bootstrap method described in HVMFS 2013:19
        """
        # Set up result class
        #        self.classification_results.add_info('parameter', self.indicator_parameter)

        # Set dataframe to use        
        #        self._set_water_body_indicator_df(water_body)

        # Get type area and return False if there is not match for the given waterbody    
        type_area = self.mapping_objects['water_body'].get_type_area_for_water_body(water_body, include_suffix=True)
        if type_area == None:
            return False, False, False, False

        wb_name = self.mapping_objects['water_body'][water_body]['WATERBODY_NAME']

        def bootstrap(value_list, n):
            result2 = []
            for i in range(1, n):
                result1 = []
                for j in range(1, len(value_list)):
                    result1.append(value_list[random.randrange(0, len(value_list) - 1)])
                result2.append(np.mean(result1))
            return result2

        # Random selection with replacement of as many values as there are station means (frac = 1)
        # TODO: spead-up! Is it possible more efficient way to get the list from the map object?

        # get data to be used for status calculation
        test = self.water_body_indicator_df[water_body].loc[
            self.water_body_indicator_df[water_body][self.indicator_parameter] == np.nan]
        df = self.water_body_indicator_df[water_body].dropna(subset=[self.indicator_parameter])  # .copy(deep = True)
        df['DEPH'] = df[['MXDEP','MNDEP']].mean(axis=1)
        df['WATER_TYPE_AREA_CODE'] = type_area
        self._add_wb_name_to_df(df, water_body)
        df.rename(columns={self.wb_id_header: self.wb_id_header + '_original'}, inplace=True)
        df[self.wb_id_header] = water_body
        year_list = df.YEAR.unique()
        station_list = df.STATN.unique()

        n = 9999
        by_year_pos_result_list = []
        by_station_result_list = []
        for station in station_list:
            # All values at station
            station_values = df.loc[df.STATN == station]  # .dropna(subset = [self.indicator_parameter])
            year_list = station_values.YEAR.unique()
            ref_value = station_values.REFERENCE_VALUE.unique()[0]
            hg_value = station_values.HG_VALUE_LIMIT.unique()[0]
            gm_value = station_values.GM_VALUE_LIMIT.unique()[0]
            mp_value = station_values.MP_VALUE_LIMIT.unique()[0]
            pb_value = station_values.PB_VALUE_LIMIT.unique()[0]

            ##### CALCLUTE MEAN BQI & EQR FOR EACH STATION  EACH YEAR #####
            station_mean_list = []
            for year in year_list:
                # all values at station in year
                station_year_values = station_values.loc[station_values.YEAR == year]
                if station_year_values.empty:
                    station_mean = np.nan
                    # global_EQR = np.nan
                    by_year_pos_result_list.append((int(year), station, station_mean, np.nan, np.nan, ref_value,
                                                    hg_value, gm_value, mp_value, pb_value))
                else:
                    station_mean = station_year_values[self.indicator_parameter].mean()
                    global_EQR, status = self._calculate_global_EQR_from_indicator_value(water_body=water_body,
                                                                                         value=station_mean,
                                                                                         REF_VALUE_LIMIT=ref_value,
                                                                                         HG_VALUE_LIMIT=hg_value,
                                                                                         GM_VALUE_LIMIT=gm_value,
                                                                                         MP_VALUE_LIMIT=mp_value,
                                                                                         PB_VALUE_LIMIT=pb_value)
                    by_year_pos_result_list.append((int(year), station, station_mean, global_EQR, status, ref_value,
                                                    hg_value, gm_value, mp_value, pb_value))
                    station_mean_list.append(station_mean)
            if len(station_mean_list) > 1:
                BQIsim = bootstrap(station_mean_list, n)
            elif len(station_mean_list) == 0:
                BQIsim = np.nan
            else:
                BQIsim = station_mean_list[0]

            percentile = np.percentile(BQIsim, 0.2)
            global_EQR, status = self._calculate_global_EQR_from_indicator_value(water_body=water_body,
                                                                                 value=percentile,
                                                                                 REF_VALUE_LIMIT=ref_value,
                                                                                 HG_VALUE_LIMIT=hg_value,
                                                                                 GM_VALUE_LIMIT=gm_value,
                                                                                 MP_VALUE_LIMIT=mp_value,
                                                                                 PB_VALUE_LIMIT=pb_value)

            by_station_result_list.append(
                (station, percentile, global_EQR, status, ref_value, hg_value, gm_value, mp_value, pb_value))

        ##### Create dataframes for saving #####
        by_year_pos = pd.DataFrame(data=by_year_pos_result_list,
                                   columns=['YEAR', 'STATN', 'BQI_station_mean', 'global_EQR', 'STATUS', 'ref_value',
                                            'hg_value', 'gm_value', 'mp_value', 'pb_value'])
        by_year_pos['WATER_BODY_NAME'] = wb_name
        by_year_pos[self.wb_id_header] = water_body
        by_year_pos['WATER_TYPE_AREA'] = type_area

        by_pos = pd.DataFrame(data=by_station_result_list,
                              columns=['STATN', 'BQI_20th percentile', 'global_EQR', 'STATUS', 'ref_value', 'hg_value',
                                       'gm_value', 'mp_value', 'pb_value'])
        by_pos['WATER_BODY_NAME'] = wb_name
        by_pos[self.wb_id_header] = water_body
        by_pos['WATER_TYPE_AREA'] = type_area

        global_EQR_by_period = np.mean(by_pos.global_EQR)
        #         STATIONS_USED =  ', '.join(by_pos.STATN.unique())
        #         STATN_count = len(by_pos.STATN.unique())
        status_by_period = self.get_status_from_global_EQR(global_EQR_by_period)
        by_period = pd.DataFrame(
            {self.wb_id_header: [water_body], 'WATER_BODY_NAME': [wb_name], 'WATER_TYPE_AREA': [type_area],
             'global_EQR': [global_EQR_by_period], 'STATUS': [status_by_period]})
        by_period['STATIONS_USED'] = ', '.join(by_pos.STATN.unique())
        by_period['STATN_count'] = len(by_pos.STATN.unique())

        min_nr_stations = self.tolerance_settings.get_min_nr_stations(water_body=water_body)
        boolean_list = by_period['STATN_count'] >= min_nr_stations
        by_period['ok'] = False
        by_period.loc[boolean_list, 'ok'] = True

        by_period['variance'] = np.nan
        by_period['p_ges'] = np.nan
        return df, by_year_pos, by_pos, by_period



###############################################################################
class IndicatorNutrients(IndicatorBase):
    """
    Class with methods common for all nutrient indicators (TOTN, DIN, TOTP and DIP). 
    """

    def __init__(self, subset_uuid, parent_workspace_object, indicator):
        super().__init__(subset_uuid, parent_workspace_object, indicator)
        self.indicator_parameter = self.parameter_list[0]
        self.salt_parameter = self.parameter_list[-1]
        #         [self.column_list.append(c) for c in ['DEPH', 'RLABO'] if c not in self.column_list]
        [self.column_list.append(c) for c in ['DEPH'] if c not in self.column_list]
        # Set dataframe to use        
        self._set_water_body_indicator_df(water_body=None)

    # ==================================================================================================================
    def _add_winter_year(self, df, winter_months):
        # print(winter_months)
        # add column for winter_YEAR
        df['winter_YEAR'] = df.apply(lambda row: row.YEAR + 1 if (row.MONTH in winter_months) else row.YEAR, axis=1)
        # if 'winter_YEAR' not in self.column_list:
        #    self.column_list = self.column_list + ['winter_YEAR']

    # ==================================================================================================================
    def calculate_status(self, water_body):
        """Calculates indicator Ecological Ratio (ER) values, for nutrients this means reference value divided by observed value.
           Transforms ER values to numeric class values (num_class)
        """
        """ Vid statusklassificering ska värden från ytvattnet användas (0-10 meter eller den övre vattenmassan om språngskiktet är grundare än 10 meter).
            Om mätningar vid ett tillfälle är utförda vid diskreta djup, 
            exempelvis 0, 5 och 10 meter ska EK-värde beräknas för varje mätning och ett medel–EK skapas för de tre djupen.
        """

        def set_value_above_one(x):
            # y = x.indicator_parameter/x.REFERENCE_VALUE
            if x > 1:
                return 1
            else:
                return x

        # ====================================================================
        if 'winter_YEAR' in self.column_list:
            self.column_list.remove('winter_YEAR')

        # get data to be used for status calculation
        if water_body not in self.water_body_indicator_df.keys():
            return False, False, False, False

        df = self.water_body_indicator_df[water_body]
        if len(df) < 1 or 'unknown' in df.WATER_BODY_NAME.unique():
            return False, False, False, False
        type_area = self.mapping_objects['water_body'].get_type_area_for_water_body(water_body, include_suffix=True)
        if type_area == None:
            return False, False, False, False
        waterdistrict = self.mapping_objects['water_body'].get_waterdistrictname_for_water_body(water_body)
        # Add column for winter year for winter indicators and set year_variable
        year_variable = 'YEAR'
        if 'winter' in self.name:
            month_list = self.parent_workspace_object.get_step_object(step=2,
                                                                      subset=self.subset).get_indicator_data_filter_settings(
                self.name).get_value(variable='MONTH_LIST', water_body=water_body)
            #            print('month_list', month_list)
            winter_months = [month for month in month_list if month > 10]
            # print(water_body, self.mapping_objects['water_body'][water_body]['WATERBODY_NAME'])
            self._add_winter_year(df, winter_months)
            year_variable = 'winter_YEAR'

        """ Calculate local_EQR (EK-värde) 
        1) NYA FÖRESKRIFTEN
        calculate local_EQR for mean of nutrient conc and salinity 0-10 m for each station.
        """
        # ENLIGT GAMLA FS SÅ SKA DETTA VARA LÄGSTA NIVÅN PÅ VILKEN DET GÖRS MEDELVÄRDEN.
        # df['local_EQR'] = df.REFERENCE_VALUE/df[self.indicator_parameter]
        # df['local_EQR'] = df['local_EQR'].apply(set_value_above_one)
        # df['global_EQR'], df['STATUS'] = zip(*df['local_EQR'].apply(self._calculate_global_EQR_from_local_EQR, water_body = water_body))

        # add dataframe to resultsclass
        #        self.classification_results.add_info(water_body, df)
        # self.classification_results[water_body].add_info('all_data', df)

        # calculate mean, max, min and count for local_EQR per measurement occasion. Here measurements on one day count as one occasion
        # .reset_index keeps all df column headers
        # TODO: what about different stations in one waterbody?

        # if len(df[self.wb_id_header].unique()) > 1:
        #     # TODO hur ska vi hantera detta om vi tillåter val av stationer i angränsande waterbody?
        #     raise Exception('more than one waterbody in dataframe')

        agg_dict1 = {self.indicator_parameter: 'mean', self.salt_parameter: 'mean',
                     'REFERENCE_VALUE': 'mean', 'HG_VALUE_LIMIT': 'mean', 'GM_VALUE_LIMIT': 'mean',
                     'MP_VALUE_LIMIT': 'mean', 'PB_VALUE_LIMIT': 'mean',
                     'DEPH': 'count', self.wb_id_header: 'max', 'WATER_BODY_NAME': 'max', 'WATER_TYPE_AREA': 'max'}
        if year_variable == 'winter_YEAR':
            agg_dict1 = {self.indicator_parameter: 'mean', self.salt_parameter: 'mean',
                         'REFERENCE_VALUE': 'mean', 'HG_VALUE_LIMIT': 'mean', 'GM_VALUE_LIMIT': 'mean',
                         'MP_VALUE_LIMIT': 'mean', 'PB_VALUE_LIMIT': 'mean',
                         year_variable: 'mean', 'DEPH': 'count', self.wb_id_header: 'max', 'WATER_BODY_NAME': 'max',
                         'WATER_TYPE_AREA': 'max'}

        agg_dict2 = {key: 'mean' for key in self.additional_parameter_list}
        agg_dict3 = {key: 'max' for key in self.column_list if
                     key not in list(agg_dict1.keys()) + list(agg_dict2.keys()) + ['SDATE', 'YEAR', 'STATN']}

        # YEAR included in groupby to get both original year and winter year in results when it is a winter indicator
        if water_body == 'WA88179174':
            print(water_body)
        by_date = df.groupby(['SDATE', 'YEAR', 'STATN']).agg({**agg_dict1, **agg_dict2, **agg_dict3}).reset_index()
        by_date.rename(columns={'DEPH': 'DEPH_count'}, inplace=True)
        check_par = False
        if type_area in ['1', '1s', '1n', '2', '3', '4', '5', '6', '25'] and 'winter' in self.name:
            if self.indicator_parameter == 'NTOT' or self.indicator_parameter == 'DIN':
                check_par = 'DIN'
            elif self.indicator_parameter == 'PTOT' or self.indicator_parameter == 'PHOS':
                check_par = 'PHOS'
            else:
                check_par = False
            if check_par:
                by_date['highest_' + check_par] = False
                for name, group in by_date.groupby(['winter_YEAR', 'STATN']):
                    idmax = group[check_par].idxmax()
                    if np.isnan(idmax):
                        continue
                    by_date.loc[idmax, 'highest_' + check_par] = True
                # print(by_date['highest_'+check_par])
            # selects only the rows where highest_check_par is True
            # by_date = by_date[by_date['highest_'+check_par]]

        #        by_date = self._add_reference_value_to_df(by_date, water_body)
        by_date['local_EQR'] = by_date.REFERENCE_VALUE / by_date[self.indicator_parameter]
        by_date['local_EQR'] = by_date['local_EQR'].apply(set_value_above_one)
        by_date['global_EQR'], by_date['STATUS'] = zip(
            *by_date['local_EQR'].apply(self._calculate_global_EQR_from_local_EQR, water_body=water_body))
        by_date['WATER_TYPE_AREA_CODE'] = type_area
        if 'NTOT' in self.indicator_parameter or 'PTOT' in self.indicator_parameter:
            cols = by_date.columns
            by_date = by_date[[c for c in cols if c not in self.additional_parameter_list]]

        # by_date[self.wb_id_header + '_original'] = by_date[self.wb_id_header].copy(deep=True)
        by_date.rename(columns={self.wb_id_header: self.wb_id_header + '_original'}, inplace=True)
        by_date[self.wb_id_header] = water_body
        # Remove occations with not enough samples
        # Or use count as a flag for what to display for the user?

        """
        2) Medelvärdet av EK för varje parameter beräknas för varje år.
        """
        agg_dict1 = {'local_EQR': 'mean', 'SDATE': 'count', self.wb_id_header: 'max', 'WATER_BODY_NAME': 'max',
                     'WATER_TYPE_AREA': 'max'}
        if check_par:
            # before grouping select only the rows where highest_check_par is True
            by_year = by_date[by_date['highest_' + check_par]].groupby([year_variable]).agg(
                {**agg_dict1}).reset_index()  # , **agg_dict2
        else:
            by_year = by_date.groupby([year_variable]).agg({**agg_dict1}).reset_index()  # , **agg_dict2
        by_year.rename(columns={'SDATE': 'DATE_count'}, inplace=True)
        by_year['global_EQR'], by_year['STATUS'] = zip(
            *by_year['local_EQR'].apply(self._calculate_global_EQR_from_local_EQR, water_body=water_body))
        try:
            by_year['STATIONS_USED'] = ', '.join(by_date.STATN.unique())
        except TypeError:
            print(by_date.STATN.unique())
            print([str(s) for s in by_date.STATN.unique()])
        by_year['STATIONS_USED'] = ', '.join(by_date.STATN.unique())

        """
        3) Medelvärdet av EK för varje parameter och vattenförekomst (beräknas för minst
        en treårsperiod)
        """
        agg_dict1 = {'local_EQR': 'mean', year_variable: 'count', 'WATER_TYPE_AREA': 'max', 'WATER_BODY_NAME': 'max', }

        by_period = by_year.groupby([self.wb_id_header]).agg({**agg_dict1}).reset_index()  # , **agg_dict2
        by_period.rename(columns={year_variable: 'YEAR_count'}, inplace=True)

        by_period['global_EQR'], by_period['STATUS'] = zip(
            *by_period['local_EQR'].apply(self._calculate_global_EQR_from_local_EQR, water_body=water_body))
        S = ', '.join(by_year.STATIONS_USED.unique())
        by_period['STATIONS_USED'] = ', '.join(set(S.split(', ')))

        min_nr_years = self.tolerance_settings.get_min_nr_years(water_body=water_body)
        boolean_list = by_period['YEAR_count'] >= min_nr_years
        by_period['ok'] = False
        by_period.loc[boolean_list, 'ok'] = True

        """
        4) Statusklassificeringen för respektive parameter görs genom att medelvärdet av
        EK jämförs med de angivna EK-klassgränserna i tabellerna 6.2-6.7. 
        """

        by_year_pos = False
        by_period['variance'] = np.nan
        by_period['p_ges'] = np.nan
        return by_date, by_year_pos, by_year, by_period
        # Add waterbody status to result class
        #        self.classification_results[water_body].add_info('local_EQR_by_date', by_date)
        #        self.classification_results[water_body].add_info('local_EQR_by_year', by_year)
        #        self.classification_results[water_body].add_info('local_EQR_by_period', by_period['mean'].get_value('mean_local_EQR'))
        #        self.classification_results[water_body].add_info('number_of_years', by_period['count'].get_value('mean_local_EQR'))
        #        self.classification_results[water_body].add_info('all_ok', all_ok)
        #
        """
        5) EK vägs samman för ingående parametrar (tot-N, tot-P, DIN och DIP) enligt
        beskrivning i föreskrift för slutlig statusklassificering av hela kvalitetsfaktorn.
        Görs i quality_factors, def calculate_quality_factor()
        """


###############################################################################
class IndicatorNutrients_SCM(IndicatorNutrients):
    """
    Class with methods common for all nutrient indicators (TOTN, DIN, TOTP and DIP). 
    """

    def __init__(self, subset_uuid, parent_workspace_object, indicator):
        super().__init__(subset_uuid, parent_workspace_object, indicator)
        self.indicator_parameter = self.parameter_list[0]
        self.salt_parameter = self.parameter_list[-1]
        # CHANGES from parentclass
        self.meta_columns = ['SDATE', 'YEAR', 'MONTH', 'STATN', self.wb_id_header, 'WATER_BODY_NAME', 'WATER_DISTRICT_NAME',
                             'WATER_TYPE_AREA', 'DEPH']
        self.column_list = self.meta_columns + self.parameter_list + self.additional_parameter_list

        # Set dataframe to use        
        self._set_water_body_indicator_df(water_body=None)


###############################################################################
class IndicatorOxygen(IndicatorBase):
    """
    Class with methods for Oxygen indicator. 
    Stations used
    Station mean wadep
    Depth at 3.5 limit, month, year
    Other stations with measurements below 3.5 limit
    """

    def __init__(self, subset_uuid, parent_workspace_object, indicator):
        super().__init__(subset_uuid, parent_workspace_object, indicator)
        self.indicator_parameter = self.parameter_list[0]
        # TODO: this indicator need information about waterbodies hypsographs (resources/mappings/hypsographs.txt)
        self.Hypsographs = self.mapping_objects['hypsographs']
        #         [self.column_list.append(c) for c in ['DEPH', 'RLABO', 'source_DOXY'] if c not in self.column_list]
        [self.column_list.append(c) for c in ['DEPH'] if c not in self.column_list]
        self.deficiency_limit = 3.5
        self.tol_BW = 5
        # Set dataframe to use   
        self._set_water_body_indicator_df(water_body=None)
        self.maxD = {}

    ############################################################################### 


    def _get_affected_area_fraction(self, df, water_body, eucd):

        # df = df[df['MONTH'].isin(list(range(1,5+1)))]
        maxD = self.maxD[water_body]
        #         wb_maxdepth = df.WADEP.max()
        #         statn = df.loc[df.WADEP.idxmax(),'STATN']
        interpolated_profile = self.interpolate(df[['DEPH', self.indicator_parameter]])
        critical_depth = interpolated_profile.loc[
            (interpolated_profile[self.indicator_parameter] <= self.deficiency_limit), 'DEPH'].min()
        #         print(critical_depth, maxD)
        if np.isnan(critical_depth):
            # concentration never below deficiency limit
            minimum_deficiency_depth = maxD
            affected_area_fraction = 0
        else:
            minimum_deficiency_depth = np.floor(critical_depth)
            if minimum_deficiency_depth > maxD:
                minimum_deficiency_depth = maxD
            affected_area_fraction = self.Hypsographs.get_area_fraction_at_depth(water_body=eucd,
                                                                             depth=minimum_deficiency_depth)
        #         print(affected_area_fraction)
        return affected_area_fraction, critical_depth

    ####################################################################################################################
    def interpolate(self, profile):
        """
        :param: dataframe with depth and oxygen at discrete depth
        :return: dataframe with depth and oxygen in 1 m intervals to original max depth, no extrapolation
        """
        interpolated_depths = np.arange(profile.DEPH.min(), profile.DEPH.max() + 1, 0.5)

        interpolated_O2 = np.interp(interpolated_depths, profile.dropna().DEPH, profile.dropna()[self.indicator_parameter])

        df_interpolated = pd.DataFrame({'DEPH': interpolated_depths, self.indicator_parameter: interpolated_O2})

        return df_interpolated.loc[df_interpolated.DEPH <= profile.DEPH.max()]

    ####################################################################################################################
    def _mean_of_quantile(self, df=None, water_body=None, month_list=None):
        """
        Calculates mean of the 25% percentile for each posisition in the waterbody using data from the given months
        """
        value = False
        if month_list:
            #            df = df[df['MONTH'].isin(list(range(1,5+1)))]
            df_copy = df[df['MONTH'].isin(month_list)]
        else:
            df_copy = df.copy()
        maxD = self.maxD[water_body]#self.Hypsographs.get_max_depth_of_water_body(water_body)
        station_depth = df_copy.WADEP.max()
        if np.isnan(station_depth):
            bottomwater_D = maxD - self.tol_BW
        else:
            bottomwater_D = station_depth - self.tol_BW
        df_BW = df_copy.loc[df_copy['DEPH'] >= bottomwater_D].dropna(subset=[self.indicator_parameter]).copy()
        no_yr = len(df_BW['YEAR'].unique())
        month_list = df_BW['MONTH'].unique()
        if no_yr >= 1:
            q = df_BW[self.indicator_parameter].quantile(0.25)
            if np.isnan(q):
                print('q', q)
                value = np.nan
            else:
                value = np.nanmean(q)
        else:
            value = np.nan
        if isinstance(value, bool):
            print(value)

        return value, no_yr, month_list

    ####################################################################################################################
    def _test1(self, df, water_body):
        """
        To decide if the water body suffers from oxygen deficiency or not.
        Takes bottomwater data for the whole year and checks if the mean of the 25% percentile is above or below limit
        """
        # all months jan-dec should be used for test1
        result, no_yr, month_list = self._mean_of_quantile(df=df, water_body=water_body, month_list=None)
        if (len(month_list) >= 7 and any([True for m in month_list if m in [12, 1, 2, 3, 4, 5]])) and no_yr >= 3:
            test1_ok = True
        else:
            test1_ok = False
        if result < 0:
            pass
        return result, no_yr, month_list, test1_ok

    ####################################################################################################################
    def _test2(self, df, water_body, skip_longterm=False):
        """
        To decide if the water body suffers from seasonal or longterm oxygen deficiency.
        Takes bottomwater data for jan-maj and for every position checks if the mean of the 25% percentile is above or below limit 
        """
        month_list = list(range(1, 5 + 1))
        result, no_yr, month_list = self._mean_of_quantile(df=df, water_body=water_body, month_list=month_list)
        self.test2_result = result
        self.test2_no_yr = no_yr
        self.test2_month_list = month_list
        if len(month_list) >= 3 and no_yr >= 3:
            test2_ok = True
        else:
            test2_ok = False
        return result, no_yr, month_list, test2_ok

        ###############################################################################

    def calculate_status(self, water_body):
        """
        Created     20180619    by Lena Viktorsson
        Updated     20180619    by Lena Viktorsson
        Method to calculate status for oxygen indicator
        """
        #        # Set dataframe to use
        df = self.water_body_indicator_df[water_body].copy(deep=True)

        # if no data        
        if len(df) < 1:
            return False, False, False, False
        # if more than one water body in dataframe, raise error      
        # if len(df[self.wb_id_header].unique()) > 1:
        #     # TODO hur ska vi hantera detta om vi tillåter val av stationer i angränsande waterbody?
        #     raise Exception('more than one waterbody in dataframe')
            # Get type area and return False if there is not match for the given waterbody
        type_area = self.mapping_objects['water_body'].get_type_area_for_water_body(water_body, include_suffix=True)
        if type_area == None:
            return False, False, False, False
        if df.empty:
            return False, False, False, False

        wb_name = self.mapping_objects['water_body'][water_body]['WATERBODY_NAME']
        wb_eucd = self.mapping_objects['water_body'][water_body]['VISS_EU_CD']
        self.maxD[water_body] = self.Hypsographs.get_max_depth_of_water_body(wb_eucd)
        wb_max_wadep = df.WADEP.max()
        wb_max_deph = df.DEPH.max()
        #         if wb_max_wadep < maxD-10 or all([np.isnan(wb_max_wadep), wb_max_deph < maxD - 10]):
        #             # TODO: change to return no BW data
        #             print('{} has no BW data. '.format(df.WATER_BODY_NAME))
        #             return False, False, False, False

        idx_list = []
        new_df = pd.DataFrame()
        for name, group in df.groupby(['STATN', 'SDATE']):
            # get stn BW, stn O2_BW, %area below 3.5, 3.5 deph
            idx = group.DEPH.dropna().idxmax()
            if np.isnan(idx):
                continue
            idx_list.append(idx)
            #             BW_DEPH = group.loc[group.idx, 'DEPH']
            #             BW_DOXY = group.loc[group.idx, self.indicator_parameter]
            affected_area_fraction, minimum_deficiency_depth = self._get_affected_area_fraction(group, water_body, eucd=wb_eucd)
            new_df = new_df.append(
                pd.DataFrame(data=[[affected_area_fraction * 100, minimum_deficiency_depth]], index=[idx],
                             columns=['AREA_PERC_BELOW_CRITICAL_DEPH', 'CRITICAL_DEPH']))

        by_date = df.ix[idx_list].copy().merge(new_df, right_index=True, left_index=True)
        by_date['MAX_DEPH_HYPSOGRAPH'] = self.maxD[water_body]
        by_date['MAX_STATN_DEPH'] = wb_max_wadep
        by_date['WATER_TYPE_AREA_CODE'] = type_area
        # by_date[self.wb_id_header + '_original'] = by_date[self.wb_id_header].copy(deep=True)
        by_date.rename(columns={self.wb_id_header: self.wb_id_header + '_original'}, inplace=True)
        by_date[self.wb_id_header] = water_body

        ######## ------------------STATUS CALCULATIONS ------------------########
        stations_below_limit = by_date.loc[
            by_date[self.indicator_parameter] < self.deficiency_limit].STATN.unique().tolist()
        stations_below_limit_str = ', '.join(stations_below_limit)
        # TODO: set 10 as self.limitBW
        if water_body == 'WA23971566':
            # TODO: add possibility from GUI to set shallowest depth to use for BW
            # this includes oxygen data from Koljöfjord from 39 m and deeper, commen max sample depth is 40 .
            by_date_deep = by_date.loc[by_date.DEPH >= 39].copy()
        else:
            by_date_deep = by_date.loc[by_date.DEPH >= (self.maxD[water_body] - 10)].copy()
        if by_date_deep.empty:
            by_period = False
        else:
            by_period = True

        if by_period:
            deepest_statns_str = ', '.join(by_date_deep.STATN.unique().tolist())
            ######## TEST 1 checks if the waterbody suffers from oxygen deficiency or not jan-dec #######################
            test1_result, test1_no_yr, test1_month_list, test1_ok = self._test1(by_date_deep, water_body)
            ######## TEST 2 checks if the waterbody suffers from oxygen deficiency or not jan-maj #######################
            test2_result, test2_no_yr, test2_month_list, test2_ok = self._test2(by_date_deep, water_body)
            ######## AREA FRACTION WITHI LOW OXYGEN #######
            mean_affected_area_fraction = by_date_deep.AREA_PERC_BELOW_CRITICAL_DEPH.mean()
            mean_critical_depth = by_date_deep.CRITICAL_DEPH.mean()

            comment = ''
            if not test1_ok:
                deficiency_type = ''
                status = ''
                global_EQR = np.nan
                comment = 'not enough data for test1 (jan-dec)'
            elif test1_result > self.deficiency_limit:
                deficiency_type = 'no_deficiency'
                status = 'HIGH'
                global_EQR = 1
                #            area_fraction_value = np.nan
            elif test1_result <= self.deficiency_limit:
                ######### TEST 2 tests the type of oxygen deficiency if status was not 'High'. ######################
                if not test2_ok:
                    deficiency_type = ''
                    status = ''
                    global_EQR = np.nan
                    comment = 'not enough data for test2 (jan-may)'
                elif test2_result > self.deficiency_limit or np.isnan(test2_result):
                    #### METHOD 1 ####
                    deficiency_type = 'seasonal'
                    global_EQR, status = self._calculate_global_EQR_from_indicator_value(water_body=water_body,
                                                                                         value=test1_result,
                                                                                         max_value=100)
                elif test2_result <= self.deficiency_limit:
                    # TODO: only use station with wadep >= maxD-10
                    #                 mean_affected_area_fraction = by_date_deep.AREA_PERC_BELOW_CRITICAL_DEPH.mean()
                    #                 mean_critical_depth = by_date_deep.CRITICAL_DEPH.mean()
                    deficiency_type = 'longterm'
                    if self.ref_settings.get_value(variable=self.wb_id_header, water_body=water_body) == water_body:
                        #### METHOD 2 ####
                        global_EQR, status = self._calculate_global_EQR_from_indicator_value(water_body=water_body,
                                                                                             value=mean_affected_area_fraction,
                                                                                             max_value=100)
                    else:
                        #### METHOD 1 #####
                        comment = 'no classboundaries defined for longterm deficieny in this waterbody, using definition of seasonal deficiency'
                        global_EQR, status = self._calculate_global_EQR_from_indicator_value(value=test1_result,
                                                                                             water_body=water_body)
            else:
                by_period = False

        if by_period:
            by_period = pd.DataFrame(
                {self.wb_id_header: [water_body], 'WATER_BODY_NAME': [wb_name], 'WATER_TYPE_AREA': [type_area],
                 'GLOBAL_EQR': [global_EQR], 'STATUS': [status], 'DEEPEST_STATNS': deepest_statns_str,
                 'MAX_WADEP': wb_max_wadep,
                 'O2 conc test1': [test1_result], 'O2 conc test2': [test2_result],
                 '% Area below conc limit': [mean_affected_area_fraction], 'Depth of conc limit': [mean_critical_depth],
                 'max depth': [self.maxD[water_body]],
                 'test1_ok': [test1_ok], 'test1_month_list': [test1_month_list], 'test1_no_yr': [test1_no_yr],
                 'test2_ok': [test2_ok], 'test2_month_list': [test2_month_list], 'test2_no_yr': [test2_no_yr],
                 'DEFICIENCY_TYPE': [deficiency_type], 'CONC_LIMIT': [self.deficiency_limit],
                 'COMMENT': [comment], 'STATNS_below_limit': stations_below_limit_str})
            by_period['variance'] = np.nan
            by_period['p_ges'] = np.nan

        return by_date_deep, by_date, False, by_period

    ############################################################################### 



###############################################################################
class IndicatorPhytoplankton(IndicatorBase):
    """
    Class with methods incommon for Phytoplankton indicators.
    """

    def __init__(self, subset_uuid, parent_workspace_object, indicator):
        super().__init__(subset_uuid, parent_workspace_object, indicator)
        #         [self.column_list.append(c) for c in ['MNDEP', 'MXDEP', 'DEPH', 'RLABO'] if c not in self.column_list]
        [self.column_list.append(c) for c in ['MNDEP', 'MXDEP', 'DEPH'] if c not in self.column_list]
        if self.name == 'indicator_chl':
            if all(x in self.get_filtered_data(subset=self.subset, step='step_2').columns for x in
                   self.parameter_list[0:-1]):
                # if data is available for all parameters, use all except SALT
                self.indicator_parameter = self.parameter_list[0:-1]
            elif all(x in self.get_filtered_data(subset=self.subset, step='step_2').columns for x in
                     self.parameter_list[1:-1]):
                # if data is available for all parameters but the first (CPHL_INTEG), use the remaining two (CPHL_INTEG_CALC and CPHL_BTL) except SALT
                self.indicator_parameter = self.parameter_list[1:-1]
                self.column_list.remove(self.parameter_list[0])
            elif self.parameter_list[0] in self.get_filtered_data(subset=self.subset, step='step_2').columns:
                # if data is available only for the first parameter (CPHL_INTEG), use only CPHL_INTEG
                self.indicator_parameter = [self.parameter_list[0]]
                self.column_list = [c for c in self.column_list if c not in self.parameter_list[1:-1]]

        self.salt_parameter = self.parameter_list[-1]
        self.notintegrate_typeareas = ['8', '9', '10', '11', '12-s', '12-n,', '13', '14', '15', '24']
        self.start_deph_max = 2
        self.end_deph_max = 11
        self.end_deph_min = 9
        # Set dataframe to use        
        self._set_water_body_indicator_df(water_body=None)

    # ==================================================================================================================
    def _get_surface_df(self, df, type_area):
        # TODO: This is now very slow since it has to look at each measurement. Can be written much faster.
        # For a start you can turn of all the if-statements and just take discrete sample or integrated.
        """
        First step before calculating EQR values and status. Collect the surface data that should be used.

        :param df:
        :param type_area:
        :return: surface dataframe, list with indeces used, comment
        """

        # --------------------------------------------------------------------------------------------------------------
        def get_surface_sample(df):
            """
            # Get a surface (<2 m) sample from available data
            # 1. Bottle sample <2 m
            # 2. Hose sample from <2 m
            # 3. Shallowest sample from bottle or hose
            :param df
            :return add_df
            """
            # ----------------------------------------------------------------------------------------------------------
            def get_hose_surface_data(df):
                """
                gets best available hose data for surface
                :param df:
                :return: add_df
                """
                comment = ''
                MXD = df.MXDEP.values[0]
                MND = df.MNDEP.values[0]
                if MXD <= max_surf_deph:
                    # max depth for hose data is from shallow depths, use this
                    value = df.loc[df.MXDEP == MXD, param]
                    add_df = df.loc[df.MXDEP == MXD].copy()
                    value_found = True
                elif MXD == np.nan and MND <= max_surf_deph:
                    # no max depth given, min depth for hose data is from shallow depths, use this
                    value = df.loc[df.MNDEP == MND, param]
                    add_df = df.loc[df.MNDEP == MND].copy()
                    value_found = True
                elif MXD <= 11:
                    # use out of bounds hose data
                    value = df.loc[df.MXDEP == MXD, param]
                    add_df = df.loc[df.MXDEP == MXD].copy()
                    value_found = True
                    comment = 'Expert judgement. This is not true surface sample'
                else:
                    return False
                add_df['comment'] = comment
                add_df['VALUE'] = value
                if 'VALUE' not in add_df.columns:
                    raise Exception(message='no VALUE key')
                return add_df
            # ----------------------------------------------------------------------------------------------------------
            comment = ''
            max_surf_deph = self.start_deph_max
            indicator_cols = ~df[indicator_list].isnull().all()
            indicator_cols = indicator_cols[np.where(indicator_cols)[0]].index[:].tolist()
            param = 'CPHL_BTL'
            value_found = False
            if param in indicator_cols:
                # There is chlorophyll bottle data
                idxmin = df.dropna(subset=[param])['DEPH'].idxmin(skipna=True)
                minD_old = df.dropna(subset=[param]).DEPH.min()
                minD = df.loc[idxmin, 'DEPH']
                if minD <= max_surf_deph:
                    # There is chlorophyll bottle data from an accepted depth
                    value_old = df.loc[df.DEPH == minD, param]
                    add_df_old = df.loc[df.DEPH == minD, ].copy()
                    value = df.loc[idxmin, param]
                    add_df = df.loc[[idxmin], :].copy()
                    add_df['comment'] = comment
                    add_df['VALUE'] = value
                    value_found = True
                else:
                    # no true surface sample from bottle, proceed to check hose data.
                    value_found = False
            if not value_found:
                # check hose data
                param_list = [p for p in ['CPHL_INTEG', 'BIOV_CONC_ALL'] if p in indicator_list]
                if len(param_list) == 1:
                    param = param_list[0]
                    if not df.dropna(subset=[param]).empty:
                    # There is hose data
                        if len(df) > 1:
                            # print('length of df > 1', df.STATN, df[param])
                            # df can be >1 if there are duplicates, then they have different sample_ID
                            add_df = False
                            for name, hose_group in df.groupby(['SAMPLE_ID']):
                                add_df_hose = get_hose_surface_data(hose_group)
                                if isinstance(add_df_hose, bool):
                                    # no hose data in the bounds given, use bottle out of depth bounds?
                                    param = 'CPHL_BTL'
                                    if param in indicator_cols:
                                        minD = df.DEPH.min()
                                        value = df.loc[df.DEPH == minD, param]
                                        add_df = df.loc[df.DEPH == minD,].copy()
                                        value_found = True
                                        comment = 'Expert judgement. This is not true surface sample'
                                        add_df['comment'] = comment
                                        add_df['VALUE'] = value
                                    else:
                                        False
                                elif isinstance(add_df, pd.DataFrame):
                                    add_df_next = add_df_hose
                                    add_df = pd.concat([add_df, add_df_next])
                                    if 'VALUE' not in add_df.columns:
                                        raise Exception(message='no VALUE key')
                                else:
                                    add_df = add_df_hose
                        else:
                            add_df = get_hose_surface_data(df)
                            if 'VALUE' not in add_df.columns:
                                raise Exception(message='no VALUE key')
                        if isinstance(add_df, bool):
                            # no hose data in the bounds given, use bottle out of depth bounds?
                            value_found = False
                        else:
                            value_found = True
            if not value_found:
                    # no hose data use bottle data from shallowest available depth
                    param = 'CPHL_BTL'
                    if param in indicator_cols:
                        minD = df.DEPH.min()
                        value = df.loc[df.DEPH == minD, param]
                        add_df = df.loc[df.DEPH == minD, ].copy()
                        value_found = True
                        comment = 'Expert judgement. This is not true surface sample'
                        add_df['comment'] = comment
                        add_df['VALUE'] = value
                    else:
                        return False

            # TODO: add value to column VALUE above and change names here
            if 'VALUE' not in add_df.columns:
                raise KeyError(message='key VALUE missing in add_df')

            if self.name == 'indicator_chl':
                add_df['CPHL_SOURCE'] = param
                add_df.rename(columns={'comment': 'CPHL_comment', 'VALUE': 'CPHL'}, inplace=True)
            else:
                add_df.rename(columns={'comment': 'BIOV_comment', 'VALUE': self.indicator_parameter[0]}, inplace=True)

            return add_df

        # --------------------------------------------------------------------------------------------------------------
        def get_integ_sample(df):
            """
            :param df
            :return add_df
            """
            # ----------------------------------------------------------------------------------------------------------
            def get_integrated(df):
                MXD = df.MXDEP.values
                MND = df.MNDEP.values
                try:
                    MXD[0]
                except IndexError:
                    print(MXD)
                if len(MND) > 1:
                    print(df.WATER_BODY_NAME, MND, MXD)
                    pass
                else:
                    MXD = MXD[0]
                    MND = MND[0]
                if MND == np.nan:
                    MND = 0
                if MND <= start_deph_max and MXD <= end_deph_max and MXD >= end_deph_min:
                    # integrated data is within depth bounds
                    value = df.loc[df.MXDEP == MXD, param]
                    if len(df[param]) != len(value.values):
                        print('df and value does not match', df[param], value.values)
                    add_df = df.loc[df[param] == value.values, ].copy()
                    add_df['comment'] = ''
                    add_df['VALUE'] = value
                    return add_df
                elif MND <= end_deph_max and MXD <= end_deph_max:
                # elif MND <= start_deph_max and MXD <= end_deph_max:
                    # check for smaller range integrated data,
                    # for delivery created on 20190307 the commented elif was used
                    value = df.loc[df.MXDEP == MXD, param]
                    add_df = df.loc[df[param] == value.values, ].copy()
                    add_df['comment'] = 'Expert judgement. Integrated data to shallow'
                    add_df['VALUE'] = value
                    return add_df

            # ----------------------------------------------------------------------------------------------------------
            start_deph_max = self.start_deph_max
            end_deph_max = self.end_deph_max
            end_deph_min = self.end_deph_min
            indicator_cols = ~df[indicator_list].isnull().all()
            indicator_cols = indicator_cols[np.where(indicator_cols)[0]].index[:].tolist()
            comment = ''
            add_df = False
            param_list = [p for p in ['CPHL_INTEG', 'CPHL_INTEG_CALC', 'BIOV_CONC_ALL'] if p in indicator_cols]
            if len(param_list) == 0:
                # no hose data
                if 'CPHL_BTL' in df.columns:
                    if not df.dropna(subset=['CPHL_BTL']).empty:
                        param = 'CPHL_BTL'
                        add_df = df.dropna(subset=[param])
                        add_df['VALUE'] = add_df[param]
                        add_df['comment'] = 'Expert judgement. Not integrated sample'
                else:
                    return False
            else:
                # check hose data
                param = param_list[0]
                df_filtered = df.dropna(subset=[param]).copy()
                df_filtered = df_filtered.loc[(df_filtered.MXDEP <= end_deph_max) & (df_filtered.MNDEP <= start_deph_max)].dropna(subset=[param])
                if df_filtered is None or df_filtered.empty:
                    # max depth of integrated data is to large or no hose data at all
                    # no hose data
                    if 'CPHL_BTL' in df.columns:
                        if not df.dropna(subset=['CPHL_BTL']).empty:
                            param = 'CPHL_BTL'
                            add_df = df.dropna(subset=[param])
                            add_df['VALUE'] = add_df[param]
                            add_df['comment'] = 'Expert judgement. Not integrated sample'
                    else:
                        return False
                if not add_df:
                    # there is integrated data in the depth interval
                    df = df_filtered
                    if len(df) > 1:
                        # there are duplicates or both hose data and calculated integrated data
                        for name, sample in df.groupby('SAMPLE_ID'):
                            if len(sample.SAMPLE_ID.values) > 1:
                                print('duplicate SAMPLE_ID {} in {}'.format(name, sample))
                                # raise Exception(message='duplicate SAMPLE_ID {} in {}'.format(name, sample))
                                return False
                            integrated = get_integrated(sample)
                            if isinstance(integrated, bool):
                                continue
                            elif isinstance(add_df, pd.DataFrame):
                                add_df_next = integrated
                                add_df = pd.concat([add_df, add_df_next])
                            else:
                                add_df = integrated
                    else:
                        add_df = get_integrated(df)
                else:
                    # no integrated data in the interval
                    # TODO: här ska letas andra data
                    return False
                    # df_filtered = df.dropna(subset=[param]).copy()
                    # df_filtered = df_filtered.loc[(df_filtered.MXDEP <= end_deph_max)].dropna(subset=[param])

            if self.name == 'indicator_chl':
                add_df['CPHL_SOURCE'] = param
                add_df.rename(columns={'comment': 'CPHL_comment', 'VALUE': 'CPHL'}, inplace=True)
            else:
                add_df.rename(columns={'comment': 'BIOV_comment', 'VALUE': self.indicator_parameter[0]}, inplace=True)
            # if len(df) > 1:
            # TODO: if this is turned on later concat of surface_df and add_df does not work, why?
            #                 temp_df = self.sld.load_df(self.name+'_replicas')
            #                 if isinstance(temp_df, pd.DataFrame):
            #                     self.sld.save_df(pd.concat([temp_df, add_df]), self.name+'_replicas', force_save_txt = True)
            #                 else:
            #                     self.sld.save_df(add_df, self.name+'_replicas', force_save_txt = True)
            #                 print(add_df, add_df.STATN)
            if 'CPHL' not in add_df.columns:
                pass
            return add_df

        # -----------------------------------------------------------------------------------

        if not isinstance(self.indicator_parameter, list):
            indicator_list = [self.indicator_parameter]
        else:
            indicator_list = self.indicator_parameter

        surface_df = pd.DataFrame()  # .from_dict({c: [] for c in df.columns})
        index_list = []
        comment = ''
        for name, group in df.groupby(['STATN', 'SDATE']):
                group_df = group.copy()
                if np.isnan(group_df.WADEP.values[0]):
                    mean_WADEP = df.loc[df.STATN == group_df.STATN.values[0], 'WADEP'].mean()
                    ix = group_df.loc[np.isnan(group_df.WADEP), 'WADEP'].index[0]
                    index_list.append(ix)
                    group_df.loc[ix, 'WADEP'] = mean_WADEP
                    comment = 'WADEP added'
                if (group_df.WADEP.min() < 12) | (type_area in self.notintegrate_typeareas and self.name == 'indicator_chl'):
                    add_df = get_surface_sample(group_df)
                else:
                    add_df = get_integ_sample(group_df)
                if isinstance(add_df, bool):
                    continue
                if 'SALT' not in add_df.columns:
                    s = self.get_closest_matching_salinity(name[1], name[0], add_df[self.wb_id_header].values[0], deph_max=self.end_deph_max)
                    add_df['SALT'] = s
                elif np.isnan(add_df.SALT.values[0]):
                    try:
                        s = self.get_closest_matching_salinity(name[1], name[0], add_df[self.wb_id_header].values[0],
                                                               deph_max=self.end_deph_max)
                    except KeyError:
                        print('cant get closest matching salinity', add_df)
                        break
                    add_df['SALT'] = s
                surface_df = pd.concat([surface_df, add_df])
        if 'CPHL' not in surface_df.columns:
            pass
        return surface_df, index_list, comment

    def calculate_status(self, water_body):
        """
        Calculates indicator Ecological Ratio (ER) values, for nutrients this means reference value divided by observed value.
        Transforms ER values to numeric class values (num_class)
        """

        def set_value_above_one(x):
            # y = x.indicator_parameter/x.REFERENCE_VALUE
            if x > 1:
                return 1
            else:
                return x

        # Set up result class
        #        self.classification_results.add_info('parameter', self.indicator_parameter)
        #        self.classification_results.add_info('salt_parameter', self.salt_parameter)

        #        self._set_water_body_indicator_df(water_body)
        # get data to be used for status calculation, not deep copy because local_EQR values are relevant to see together with data
        if water_body not in self.water_body_indicator_df.keys():
            return False, False, False, False
        df = self.water_body_indicator_df[water_body]
        #         if self.name == 'chl' and len(df.dropna(subset = [self.indicator_parameter])) == 0 and len(df.dropna(subset = [self.parameter_list[1]])) > 0:
        #             indicator_parameter = self.parameter_list[1]
        #         else:
        #             indicator_parameter = self.parameter_list[0]

        if len(df) < 1:
            return False, False, False, False

        # if len(df[self.wb_id_header].unique()) > 1:
        #     # TODO hur ska vi hantera detta om vi tillåter val av stationer i angränsande waterbody?
        #     raise Exception('more than one waterbody in dataframe')

        type_area = self.mapping_objects['water_body'].get_type_area_for_water_body(water_body, include_suffix=True)
        if type_area == None:
            return False, False, False, False

        #
        #        self._add_wb_name_to_df(df, water_body)
        """ Calculate local_EQR (EK-värde)
        """
        """ 1) Beräkna local_EQR (EK-värde) för varje enskilt prov utifrån (ekvationer för) referensvärden i tabellerna 6.2-6.7.
            Beräkna local_EQR (EK-värde) för varje mätning och sedan ett medel-EK för varje specifikt mättillfälle.
            TO BE UPDATED TO local_EQR for mean of nutrient conc and salinity 0-10 m.
        """
        surface_df, index_list, comment = self._get_surface_df(df, type_area)
        # save the selected indices from df to a txt file
        save_df = df.loc[index_list].copy()
        save_df['COMMENT'] = comment
        if not save_df.empty:
            if os.path.exists(self.sld.directory + self.name + '_changed_indices.txt'):
                temp_df = self.sld.load_df(self.name + '_changed_indices')
                self.sld.save_df(pd.concat([temp_df, save_df]), self.name + '_changed_indices')
            else:
                self.sld.save_df(save_df, self.name + '_changed_indices')

        if surface_df.empty:
            return False, False, False, False

        self._add_boundaries_to_df(surface_df, water_body)

        if self.name == 'indicator_chl':
            indicator_parameter = 'CPHL'
        else:
            indicator_parameter = self.indicator_parameter
        #         agg_dict1 = {indicator_parameter: 'mean', self.salt_parameter: 'mean',
        #                      'REFERENCE_VALUE': 'mean', 'HG_VALUE_LIMIT': 'mean', 'GM_VALUE_LIMIT': 'mean', 'MP_VALUE_LIMIT': 'mean', 'PB_VALUE_LIMIT': 'mean',
        #                       'DEPH': 'count', 'VISS_EU_CD': 'max', 'WATER_BODY_NAME': 'max', 'WATER_TYPE_AREA': 'max'}

        #
        #         by_date = surface_df.groupby(['SDATE', 'YEAR', 'STATN']).agg({**agg_dict1, **agg_dict2}).reset_index()
        #         by_date.rename(columns={'DEPH':'DEPH_count'}, inplace=True)
        # #         by_date = compile_surface_values(water_body)
        #         by_date = self._add_reference_value_to_df(by_date, water_body)
        #
        save_columns = surface_df.columns.tolist()
        if self.name == 'indicator_chl':
            [save_columns.remove(c) for c in self.indicator_parameter]
        surface_df = surface_df[save_columns]
        surface_df['WATER_TYPE_AREA_CODE'] = type_area
        surface_df['local_EQR'] = surface_df.REFERENCE_VALUE / surface_df[indicator_parameter]
        surface_df['local_EQR'] = surface_df['local_EQR'].apply(set_value_above_one)
        surface_df['global_EQR'], surface_df['STATUS'] = zip(
            *surface_df['local_EQR'].apply(self._calculate_global_EQR_from_local_EQR, water_body=water_body))
        # by_date.set_index(keys = 'VISS_EU_CD', append =True, drop = False, inplace = True)
        # surface_df[self.wb_id_header + '_original'] = surface_df[self.wb_id_header].copy(deep=True)
        surface_df.rename(columns={self.wb_id_header: self.wb_id_header + '_original'}, inplace=True)
        surface_df[self.wb_id_header] = water_body
        """ 2) Medelvärdet av EK för parametern beräknas för varje år och station.
        """
        agg_dict1 = {'local_EQR': 'mean', indicator_parameter: 'mean', self.salt_parameter: 'mean', 'SDATE': 'count',
                     self.wb_id_header: 'max', 'VISS_EU_CD': 'max', 'WATER_BODY_NAME': 'max', 'WATER_TYPE_AREA': 'max',
                     'WATER_TYPE_AREA_CODE': 'max'}
        if len(self.additional_parameter_list) > 0:
            agg_dict2 = {key: 'mean' for key in self.additional_parameter_list}
        else:
            agg_dict2 = {}

        by_year_pos = surface_df.groupby(['YEAR', 'STATN']).agg({**agg_dict1, **agg_dict2}).reset_index()
        by_year_pos.rename(columns={'SDATE': 'DATE_count'}, inplace=True)
        by_year_pos['global_EQR'], by_year_pos['STATUS'] = zip(
            *by_year_pos['local_EQR'].apply(self._calculate_global_EQR_from_local_EQR, water_body=water_body))
        # by_year_pos .set_index(keys = 'VISS_EU_CD', append =True, drop = False, inplace = True)

        """
        3) Medelvärdet av EK för parametern beräknas för varje år.
        """
        agg_dict1 = {'local_EQR': 'mean', indicator_parameter: 'mean', self.salt_parameter: 'mean', 'STATN': 'count',
                     self.wb_id_header: 'max', 'VISS_EU_CD': 'max', 'WATER_BODY_NAME': 'max', 'WATER_TYPE_AREA': 'max',
                     'WATER_TYPE_AREA_CODE': 'max'}

        by_year = by_year_pos.groupby(['YEAR']).agg({**agg_dict1}).reset_index()  # , **agg_dict2
        by_year.rename(columns={'STATN': 'STATN_count'}, inplace=True)
        by_year['global_EQR'], by_year['STATUS'] = zip(
            *by_year['local_EQR'].apply(self._calculate_global_EQR_from_local_EQR, water_body=water_body))
        by_year['STATIONS_USED'] = ', '.join(by_year_pos.STATN.unique())
        # by_year.set_index(keys = 'VISS_EU_CD', append =True, drop = False, inplace = True)

        """
        4) Medelvärdet av EK för varje parameter och vattenförekomst (beräknas för minst
        en treårsperiod)
        """
        agg_dict1 = {'local_EQR': 'mean', indicator_parameter: 'mean', self.salt_parameter: 'mean', 'YEAR': 'count',
                     'YEAR': 'count', 'VISS_EU_CD': 'max', 'WATER_BODY_NAME': 'max', 'WATER_TYPE_AREA': 'max',
                     'WATER_TYPE_AREA_CODE': 'max'}

        by_period = by_year.groupby([self.wb_id_header]).agg({**agg_dict1}).reset_index()  # , **agg_dict2
        by_period['YEARS_USED'] = ', '.join(map(str, by_year.YEAR.unique()))
        by_period.rename(columns={'YEAR': 'YEAR_count'}, inplace=True)
        by_period['global_EQR'], by_period['STATUS'] = zip(
            *by_period['local_EQR'].apply(self._calculate_global_EQR_from_local_EQR, water_body=water_body))
        S = ', '.join(by_year.STATIONS_USED.unique())
        by_period['STATIONS_USED'] = ', '.join(set(S.split(', ')))

        min_nr_years = self.tolerance_settings.get_min_nr_years(water_body=water_body)
        boolean_list = by_period['YEAR_count'] >= min_nr_years
        by_period['ok'] = False
        by_period.loc[boolean_list, 'ok'] = True

        """
        4) Statusklassificeringen för respektive parameter görs genom att medelvärdet av
        EK jämförs med de angivna EK-klassgränserna i tabellerna 6.2-6.7. 
        """
        by_period['variance'] = np.nan
        by_period['p_ges'] = np.nan
        return surface_df, by_year_pos, by_year, by_period


###############################################################################                
class IndicatorPhytplanktonSat(IndicatorPhytoplankton):
    """
    Class inheriting from IndicatorPhytoplankton adopted to chlorophyll from satellite
    """

    def __init__(self, subset_uuid, parent_workspace_object, indicator):
        IndicatorBase.__init__(self, subset_uuid, parent_workspace_object, indicator)

        self.column_list = self.meta_columns + self.parameter_list + self.additional_parameter_list  # + ['MS_CD']
        self.indicator_parameter = self.parameter_list[0]
        self.salt_parameter = self.parameter_list[-1]

        self._set_water_body_indicator_df(water_body=None)

    def _get_surface_df(self, df, type_area):
        """

        :param df:
        :param type_area:
        :return: surface dataframe, list with indices used, comment
        """
        surface_df = df.copy()
        surface_df['CPHL_SOURCE'] = self.indicator_parameter
        index_list = []
        comment = ''

        return surface_df, index_list, comment


#     def _get_integ_def(self, df, type_area):
#         
#         return self._get_surface_df(df, type_area) 

###############################################################################
class IndicatorSecchi(IndicatorBase):
    """
    Class with methods for Secchi indicator. 
    """

    def __init__(self, subset_uuid, parent_workspace_object, indicator):
        super().__init__(subset_uuid, parent_workspace_object, indicator)
        self.indicator_parameter = self.parameter_list[0]
        self.salt_parameter = self.parameter_list[-1]
        #         [self.column_list.append(c) for c in ['DEPH', 'RLABO'] if c not in self.column_list]
        [self.column_list.append(c) for c in ['DEPH'] if c not in self.column_list]
        # Set dataframe to use        
        self._set_water_body_indicator_df(water_body=None)

    ###############################################################################   
    def calculate_status(self, water_body):
        """
        Calculates indicator Ecological Ratio (ER) values, for nutrients this means reference value divided by observed value.
        Transforms ER values to numeric class values (num_class)
        tolerance_filters is a dict with tolerance filters for the 
        """
        """
        Vid statusklassificering ska värden från ytvattnet användas (0-10 meter eller den övre vattenmassan om språngskiktet är grundare än 10 meter).
        Om mätningar vid ett tillfälle är utförda vid diskreta djup, 
        exempelvis 0, 5 och 10 meter ska EK-värde beräknas för varje mätning och ett medel–EK skapas för de tre djupen.
        """

        def set_value_above_one(x):
            # y = x.indicator_parameter/x.REFERENCE_VALUE
            if x > 1:
                return 1
            else:
                return x

        # get data to be used for status calculation, not deep copy because local_EQR values are relevant to see together with data
        if water_body not in self.water_body_indicator_df.keys():
            return False, False, False, False
        df = self.water_body_indicator_df[water_body]
        if len(df) < 1:
            return False, False, False, False

        # if len(df[self.wb_id_header].unique()) > 1:
        #     # TODO hur ska vi hantera detta om vi tillåter val av stationer i angränsande waterbody?
        #     raise Exception('more than one waterbody in dataframe')

        type_area = self.mapping_objects['water_body'].get_type_area_for_water_body(water_body, include_suffix=True)
        if type_area == None:
            return False, False, False, False

        #        self._add_wb_name_to_df(df, water_body)
        # add dataframe to resultsclass
        #        self.classification_results.add_info(water_body, df)

        """ 
        1) Beräkna local_EQR för varje enskilt prov.
        
        """
        #        agg_dict1 = {self.indicator_parameter: 'mean', self.salt_parameter: 'mean', 'DEPH': 'count', 'VISS_EU_CD': 'max', 'WATER_BODY_NAME': 'max', 'WATER_TYPE_AREA': 'max'}
        agg_dict1 = {self.indicator_parameter: 'mean', self.salt_parameter: 'mean',
                     'REFERENCE_VALUE': 'mean', 'HG_VALUE_LIMIT': 'mean', 'GM_VALUE_LIMIT': 'mean',
                     'MP_VALUE_LIMIT': 'mean', 'PB_VALUE_LIMIT': 'mean',
                     self.wb_id_header: 'max', 'VISS_EU_CD': 'max', 'WATER_BODY_NAME': 'max', 'WATER_TYPE_AREA': 'max',
                     'WATER_DISTRICT_NAME': 'max'}
        agg_dict2 = {key: 'mean' for key in self.additional_parameter_list}
        agg_dict3 = {key: 'max' for key in self.column_list if
                     key not in list(agg_dict1.keys()) + list(agg_dict2.keys()) + ['SDATE', 'YEAR', 'STATN']}

        by_date = df.groupby(['SDATE', 'YEAR', 'STATN']).agg({**agg_dict1, **agg_dict2, **agg_dict3}).reset_index()
        #         by_date.rename(columns={'DEPH':'DEPH_count'}, inplace=True)
        #        by_date = self._add_reference_value_to_df(df, water_body)
        by_date['local_EQR'] = by_date[self.indicator_parameter] / by_date.REFERENCE_VALUE
        #        by_date['local_EQR'] = by_date['local_EQR'].apply(set_value_above_one)
        by_date['global_EQR'], by_date['STATUS'] = zip(
            *by_date['local_EQR'].apply(self._calculate_global_EQR_from_local_EQR, water_body=water_body))
        by_date['WATER_TYPE_AREA_CODE'] = type_area

        #by_date[self.wb_id_header + '_original'] = by_date[self.wb_id_header].copy(deep=True)
        by_date.rename(columns={self.wb_id_header: self.wb_id_header + '_original'}, inplace=True)
        by_date[self.wb_id_header] = water_body
        #        df['local_EQR'] = df[self.indicator_parameter]/df.REFERENCE_VALUE
        #        df['local_EQR'] = df['local_EQR'].apply(set_value_above_one)
        #        df['global_EQR'], df['STATUS'] = zip(*df['local_EQR'].apply(self._calculate_global_EQR_from_local_EQR, water_body = water_body))
        #

        by_year_pos = False
        by_year = False
        """
        2) Medelvärdet av local_EQR för varje siktdjup och vattenförekomst (beräknas för minst
        en treårsperiod)
        """
        agg_dict1 = {'local_EQR': 'mean', self.indicator_parameter: 'mean', 'YEAR': 'nunique', 'VISS_EU_CD': 'max',
                     'WATER_BODY_NAME': 'max', 'WATER_TYPE_AREA': 'max', 'WATER_TYPE_AREA_CODE': 'max',
                     'WATER_DISTRICT_NAME': 'max'}
        if len(self.additional_parameter_list) > 0:
            agg_dict2 = {key: 'mean' for key in self.additional_parameter_list}
        else:
            agg_dict2 = {}

        by_period = by_date.groupby([self.wb_id_header]).agg({**agg_dict1}).reset_index()  # , **agg_dict2
        by_period['YEARS_USED'] = ', '.join(map(str, by_date.YEAR.unique()))
        by_period.rename(columns={'YEAR': 'YEAR_count'}, inplace=True)
        by_period['global_EQR'], by_period['STATUS'] = zip(
            *by_period['local_EQR'].apply(self._calculate_global_EQR_from_local_EQR, water_body=water_body))
        by_period['STATIONS_USED'] = ', '.join(by_date.STATN.unique())

        min_nr_years = self.tolerance_settings.get_min_nr_years(water_body=water_body)
        boolean_list = by_period['YEAR_count'] >= min_nr_years
        by_period['ok'] = False
        by_period.loc[boolean_list, 'ok'] = True

        by_period['variance'] = np.nan
        by_period['p_ges'] = np.nan
        return by_date, by_year_pos, by_year, by_period


###############################################################################
class IndicatorSecchiSat(IndicatorSecchi):
    """
    Class with methods for Secchi indicator. 
    """

    def __init__(self, subset_uuid, parent_workspace_object, indicator):
        IndicatorBase.__init__(self, subset_uuid, parent_workspace_object, indicator)

        self.column_list = self.meta_columns + self.parameter_list + self.additional_parameter_list  # + ['MS_CD']
        self.indicator_parameter = self.parameter_list[0]
        self.salt_parameter = self.parameter_list[-1]

        self._set_water_body_indicator_df(water_body=None)

    ###############################################################################


if __name__ == '__main__':
    print('=' * 50)
    print('Running module "indicators.py"')
    print('-' * 50)
    print('')

    core.ParameterList()

    raw_data_file_path = 'D:/Utveckling/g_EKOSTAT_tool/test_data/raw_data/data_BAS_2000-2009.txt'

    first_data_filter_file_path = 'D:/Utveckling/g_EKOSTAT_tool/test_data/filters/first_data_filter.txt'
    first_filter = core.DataFilter('First filter', file_path=first_data_filter_file_path)

    winter_data_filter_file_path = 'D:/Utveckling/g_EKOSTAT_tool/test_data/filters/winter_data_filter.txt'
    winter_filter_1 = core.DataFilter('winter_filter', file_path=winter_data_filter_file_path)

    tolerance_filter_file_path = 'D:/Utveckling/g_EKOSTAT_tool/test_data/filters/tolerance_filter_template.txt'

    raw_data = core.DataHandler('raw')
    raw_data.add_txt_file(raw_data_file_path, data_type='column')

    filtered_data = raw_data.filter_data(first_filter)

    print('-' * 50)
    print('done')
    print('-' * 50)
