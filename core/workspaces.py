# -*- coding: utf-8 -*-
"""
Created on Fri Sep  8 21:47:05 2017

@author: a002087
"""

import os
import shutil
import sys
import datetime
import codecs
import pandas as pd
import uuid
import re
import pathlib
import time
from core.load import SaveLoadDelete

current_path = os.path.dirname(os.path.realpath(__file__))[:-4]
if current_path not in sys.path:
    sys.path.append(current_path)

import core
import core.exceptions as exceptions

"""
Module contains classes related to the structure of a workspace-directory. 
WorkSpace is the top class and contains one WorkStep-object representing step_0 
and one or several Subset-objects. Each Subset contains several WorkStep-objects 
for step_1, step_2....etc. 

All calls from outside this module should be made to the WorkSpace instance. 
If information in subsets or steps is needed the WorkSpace-class should be 
updated to retrieve this information (data should be passt on hierarchically in 
the data structure) 

Be aware that classes in this module are dependent on the directory and file 
structure of a Workspace. Altering the structure of the workspace directory  
tree 
"""

###############################################################################
class WorkStep(object):
    """
    A WorkStep holds information about the file structure in a step-directory 
    and contains all methodes operating on a specific workstep. 
    """
    def __init__(self, 
                 name=None, 
                 parent_directory=None, 
                 mapping_objects={}, 
                 parent_workspace_object=None, 
                 parent_subset_object=None):
        if not all([name, parent_directory]): 
            return 
        name = get_step_name(name)
        self.paths = {}
        self.name = name 
        self.paths['parent_directory'] = parent_directory 
        self.paths['step_directory'] = '/'.join([self.paths['parent_directory'], self.name]) 
        self.parent_workspace_object = parent_workspace_object
        self.parent_subset_object = parent_subset_object
        self.wb_id_header = self.parent_workspace_object.wb_id_header
        
        """ 
        Input argument mapping_objects is a dictionary since there might be several mapping objects in the future. 
        We do not want to (?) load mapping objects individually in each sub-object to save memory. 
        """
        self.mapping_objects = mapping_objects 
        
        self._initiate_attributes()
        
        self._set_directories()
        
        self._create_folder_structure()
        self.load_all_files()
        self._check_folder_structure()     
           
        
#        print('Initiating WorkStep: {}'.format(self.paths['step_directory']))    
        
    #==========================================================================
    def _create_folder_structure(self):
        """
        Sets up the needed folder structure for the workstep. 
        Folders are added if they dont exist. 
        """
        if not os.path.exists(self.paths['step_directory']): 
            os.makedirs(self.paths['step_directory'])
            
        for path in self.paths['directory_paths'].values():
            if not os.path.exists(path):
                os.makedirs(path)
        
    #==========================================================================
    def _create_file_paths(self): 
        """
        Builds file paths for: 
            indicator_settings
        """
        self.paths['indicator_settings_paths'] = {}
        for file_name in os.listdir(self.paths['directory_paths']['indicator_settings']): 
            if file_name.endswith('.set'):
                file_path = '/'.join([self.paths['directory_paths']['indicator_settings'], file_name])
                indicator = file_name.split('.')[0]
                self.paths['indicator_settings_paths'][indicator] = file_path
        
    #==========================================================================
    def _check_folder_structure(self):
        #TODO: make check of workspace folder structure
        all_ok = True
        for key, item in self.paths['directory_paths'].items():
            if os.path.isdir(item):
                continue
            else:
                all_ok = False
                try:
                    # MW: Does not work for me in Spyder
                    raise('PathError')
                except:
                    pass
                self._logger.debug('no folder set for: {}'.format(item))
                
        return all_ok
        
    #==========================================================================
    def _initiate_attributes(self): 
        """ 
        Updated 20180720    by Magnus Wenzer
        
        Load attributes 
        """
        self.data_filter = None
        self.indicator_settings = {} 
        self.water_body_filter = None
        
        self.allowed_data_filter_steps = ['step_0', 'step_1']
        self.allowed_indicator_settings_steps = ['step_2'] 
        self.allowed_indicator_calculation_steps = ['step_3']
        
        self.result_data = {}
        
        
    #==========================================================================
    def _change_ok(self): 
        """
        Check to make sure that the default 
        """
        if self.parent_subset_object and self.parent_workspace_object.alias == 'default_workspace':
            self._logger.debug('Not allowed to change default workspace!')
            return False
        elif self.parent_subset_object and self.parent_subset_object.alias == 'default_subset':
            self._logger.debug('Not allowed to change default subset!')
            return False
        return True
    
    
    #==========================================================================
    def _set_directories(self):
        #set paths
        self.paths['directory_paths'] = {}
        self.paths['directory_paths']['data_filters'] = self.paths['step_directory'] + '/data_filters'
        self.paths['directory_paths']['settings'] = self.paths['step_directory'] + '/settings'
        self.paths['directory_paths']['indicator_settings'] = self.paths['step_directory'] + '/settings/indicator_settings'
        self.paths['directory_paths']['water_body_station_filter'] = self.paths['step_directory'] + '/settings/water_body'
        self.paths['directory_paths']['output'] = self.paths['step_directory'] + '/output'
        self.paths['directory_paths']['results'] = self.paths['step_directory'] + '/output/results'
    
    
    #==========================================================================
    def add_files_from_workstep(self, step_object=None, overwrite=False):
        """
        Copy files from given workstep. Option to overwrite or not. 
        This method shold generaly be used when copying step_0 or a whole subset. 
        DONT USE FOR COPYING SINGLE STEPS NUMBERED 1 and up. 
        """ 
        for from_file_path in step_object.get_all_file_paths_in_workstep():
            to_file_path = from_file_path.replace(step_object.paths['step_directory'], self.paths['step_directory']) 
            if os.path.exists(to_file_path) and not overwrite:
                continue
            to_directory = os.path.dirname(to_file_path)
            if not os.path.exists(to_directory):
                # If directory has been added in later versions of the ekostat calculator
                os.makedirs(to_directory) 
            # Copy file
            shutil.copy(from_file_path, to_file_path)
        
        self.load_all_files()    
    
    
    #==========================================================================
    def calculate_status(self, indicator_list = None, water_body_list = None):
        """
        Created     20180613    by Lena Viktorsson
        Calls calculate_status for each indicator object and returns the result for each waterbody as dataframes in a dict
        """
        if self.name != 'step_3':
            return False
        
        if water_body_list == None:
            water_body_list = self.parent_workspace_object.get_filtered_data(step='step_2',
                                                                             subset=self.parent_subset_object.unique_id)[self.wb_id_header].unique()
        if not len(water_body_list):
            #raise Error?
            print('no waterbodies in filtered data')
            return False
        
        #---------------------------------------------------------------------    
        def concat_df(df, save_df, filename, water_body, indicator_object):
            #concatenate results
            if type(save_df) is pd.DataFrame:
                if water_body in save_df[self.wb_id_header].unique():
                    save_df.drop(save_df.loc[save_df[self.wb_id_header] == water_body].index, inplace = True)
                save_df = pd.concat([save_df, df])
            elif os.path.exists(indicator_object.result_directory + filename + '.txt'):
                save_df = indicator_object.sld.load_df(file_name = filename)
                if water_body in save_df[self.wb_id_header].unique():
                    save_df.drop(save_df.loc[save_df[self.wb_id_header] == water_body].index, inplace = True)
                save_df = pd.concat([save_df, df])
            else:
                save_df = df
            return save_df
        #---------------------------------------------------------------------
        
        if indicator_list == None:
            indicator_list = self.parent_workspace_object.available_indicators
            if indicator_list == None:
                indicator_list = self.parent_workspace_object.get_available_indicators(subset = self.parent_subset_object.unique_id, step = 2)
            
            
        for indicator in indicator_list:
            status_by_date = False
            status_by_year_pos = False
            status_by_year = False
            status_by_period = False
            indicator_name = self.indicator_objects[indicator].name
            print(indicator_name)
            t_ind = time.time()
            by_date, by_year_pos, by_year, by_period = False, False, False, False
            for water_body in dict.fromkeys(water_body_list,True):
                #print(water_body)
#                t_wb = time.time()
                if water_body not in self.indicator_objects[indicator].water_body_indicator_df.keys():
                    continue
                #TODO:  Here is the main calculate status call.
                # - I have thought about to put the loop over waterbodies in the IndicatorBase class.
                # - the result in by_date is really a combination of the dataframe with original data and "results" for each date.
                #   It might be better to get the data part in a dataframe separately and the add the results later. I would like to discuss this.
                # - for the user (web interface at least) it is only the bu_date and by_period results that are relevant.
                #   The other steps are good if I can access when developing with the calculation code but should not be needed for the regular user
                by_date, by_year_pos, by_year, by_period = self.indicator_objects[indicator].calculate_status(water_body = water_body)
#                time_wb = time.time() - t_wb
#                print('-'*50)
#                print('Total time to calculate status for water body {}:'.format(water_body), time_wb)
#                print('-'*50)
                if type(by_date) is not bool:
                    status_by_date = concat_df(by_date, status_by_date, 'indicator_' + indicator_name + '-by_date',
                          water_body, self.indicator_objects[indicator])
                if type(by_year_pos) is not bool:
                    status_by_year_pos = concat_df(by_year_pos, status_by_year_pos, indicator_name + '-by_year_pos',
                          water_body, self.indicator_objects[indicator])
                if type(by_year) is not bool:
                    status_by_year = concat_df(by_year, status_by_year, 'indicator_' + indicator_name + '-by_year',
                          water_body, self.indicator_objects[indicator])
                if type(by_period) is not bool:
                    status_by_period = concat_df(by_period, status_by_period, 'indicator_' + indicator_name + '-by_period',
                          water_body, self.indicator_objects[indicator])

            
            time_ind = time.time() - t_ind
            print('-'*50)
            print('Total time to calculate status for indicator {}:'.format(indicator), time_ind)
            print('-'*50)    
            
            if type(status_by_date) is not bool:  
                status_by_date['new_index'] = [str(ix) + '_' + wb for ix, wb in zip(status_by_date.index,
                                                                                   status_by_date[self.wb_id_header])]
                status_by_date.set_index(keys = 'new_index')                                
                self.indicator_objects[indicator].sld.save_df(status_by_date, file_name = indicator_name + '-by_date',
                                                              force_save_txt=True)
            if type(status_by_year_pos) is not bool:
                status_by_year_pos['new_index'] = [str(ix) + '_' + wb for ix, wb in zip(status_by_year_pos.index,
                                                                                       status_by_year_pos[self.wb_id_header])]
                status_by_year_pos.set_index(keys = 'new_index')
                self.indicator_objects[indicator].sld.save_df(status_by_year_pos, file_name = indicator_name + '-by_year_pos',
                                                              force_save_txt=True)
            if type(status_by_year) is not bool:
                status_by_year['new_index'] = [str(ix) + '_' + wb for ix, wb in zip(status_by_year.index,
                                                                                   status_by_year[self.wb_id_header])]
                status_by_year.set_index(keys = 'new_index')                                
                self.indicator_objects[indicator].sld.save_df(status_by_year, file_name = indicator_name + '-by_year',
                                                              force_save_txt=True)
            if type(status_by_period) is not bool:
                status_by_period['new_index'] = [str(ix) + '_' + wb for ix, wb in zip(status_by_period.index,
                                                                                     status_by_period[self.wb_id_header])]
                status_by_period.set_index(keys = 'new_index')                                
                self.indicator_objects[indicator].sld.save_df(status_by_period, file_name = indicator_name + '-by_period',
                                                              force_save_txt=True)
        
        
    #==========================================================================
    def calculate_quality_element(self, quality_element=None):
        
        class_name = self.parent_workspace_object.mapping_objects['quality_element'].indicator_config.loc['qe_'+quality_element.lower()]['indicator_class']
        print(class_name)
        
        if not hasattr(self, 'quality_element'):
            self.quality_element = {}
        #print(class_name)
        try:
            class_ = getattr(core, class_name)
        except AttributeError as e:
            raise AttributeError('{}\nClass does not exist'.format(e))
        #print(class_)
        #instance = class_()
        # add indicator objects to dictionary
        self.quality_element[quality_element] = class_(subset_uuid=self.parent_subset_object.unique_id, 
                                                       parent_workspace_object = self.parent_workspace_object,
                                                       quality_element = quality_element)
        
        #self.quality_element[quality_element].calculate_quality_factor()
        self.quality_element[quality_element].calculate_quality_factor()
            
    #==========================================================================
    def get_all_file_paths_in_workstep(self): 
        """
        Returns a sorted list of all file paths in the workstep tree. 
        Generally this method is used when copying the workstep. 
        """
        file_list = []
        for root, dirs, files in os.walk(self.paths['step_directory']): 
                for f in files:
                    file_list.append('/'.join([root, f]).replace('\\', '/'))
        return sorted(file_list)
    
    #==========================================================================
    def get_data_filter_object(self): 
        if self.name not in self.allowed_data_filter_steps:
            return False
        return self.data_filter
    
    
    #==========================================================================
    def get_data_filter_info(self): 
        """
        Returns a dict with data filter names as keys. 
        Every key contains a list of the active filters. 
        """
        return self.data_filter.get_filter_info()
        
    
    #==========================================================================
    def get_water_body_filter_object(self):
        
        return self.water_body_filter

    # ==========================================================================
    def get_water_body_station_filter_object(self):
        return self.water_body_station_filter
    
    #==========================================================================
    def get_indicator_data_filter_settings(self, indicator): 
        """
        Returns the data filter settings for the given indicator. 
        """
        if self.name not in self.allowed_indicator_settings_steps:
            return False
        return self.indicator_data_filter_settings.get(indicator, False)
    
    #==========================================================================
    def get_indicator_tolerance_settings(self, indicator): 
        """
        Returns the tolerance settings for the given indicator. 
        """
        if self.name not in self.allowed_indicator_settings_steps:
            return False
        return self.indicator_tolerance_settings.get(indicator, False) 
    
    #==========================================================================
    def get_indicator_ref_settings(self, indicator): 
        """
        Returns the reference settings for the given indicator. 
        """
        if self.name not in self.allowed_indicator_settings_steps:
            return False
        return self.indicator_ref_settings.get(indicator, False)
    
    # #==========================================================================
    # def get_water_body_station_filter(self):
    #     return self.water_body_station_filter
        
    #==========================================================================
    def get_indicator_settings_name_list(self):
        return sorted(self.indicator_settings.keys())
   
    #==========================================================================
    def indicator_setup(self, indicator_list=None):  
        """
        when step 3 is initiated indicator objects should be instantiated for all  indicators selected in step 2 as default
        where do we save info on selected indicators? in step_2/datafilters folder?
        We can calculate all indicators available but then the indicator selection is useless with regards to saving time for the user.
        """ 
        """
        Created:        20180215     by Lena
        Last modified:  20180913     by Magnus
        create dict containing indicator objects according to data availability or choice?
        Should be run accesed only for step 3.
        """ 
        subset_unique_id =self.parent_subset_object.unique_id
        # TODO: assert step 3
        
        if indicator_list == None:

            indicator_list = self.parent_workspace_object.available_indicators
            if indicator_list == None:
                indicator_list = self.parent_workspace_object.get_available_indicators(subset=subset_unique_id, step=2)
        if not hasattr(self, 'indicator_objects'):
            self.indicator_objects = {}
        indicators = dict.fromkeys(indicator_list)
        for indicator in indicators:
            t_start = time.time()
            class_name = self.parent_workspace_object.mapping_objects['quality_element'].indicator_config.loc[indicator]['indicator_class']
            #print(class_name)

            try:
                class_ = getattr(core, class_name)
            except AttributeError as e:
                raise exceptions.MissingClassForIndicator(message=indicator)
#                raise AttributeError('{}\nClass does not exist'.foramt(e))
            #print(class_)
            #instance = class_()
            # add indicator objects to dictionary
            self.indicator_objects[indicator] = class_(subset_uuid = subset_unique_id, 
                                                                      parent_workspace_object = self.parent_workspace_object,
                                                                      indicator = indicator)
            time_ind = time.time() - t_start
            print('-'*50)
            print('Total time to set up indicator object indicator {}:'.format(indicator), time_ind)
            print('-'*50)   
#            self.indicator_objects[indicator] = core.IndicatorBase(subset = subset_unique_id, 
#                                                                      parent_workspace_object = self.parent_workspace_object,
#                                                                      indicator = indicator)
            
    #==========================================================================
    def load_all_files(self): 
        self._create_file_paths()
        self.load_data_filter()
        self.load_indicator_settings_filters()
        self.load_water_body_station_filter()
        
        
    #==========================================================================
    def load_data_filter(self):
        """
        Load all settings files in the current WorkSpace filter folder... 
        """
#        print('STEP = ', self.name)
        self.data_filter = core.DataFilter(self.paths['directory_paths']['data_filters'], 
                                           mapping_objects=self.mapping_objects) 
    
    
    #==========================================================================
    def load_water_body_filter_object(self):
        """
        Load filter object for waterbodies
        """
        self.water_body_filter = core.WaterBodyFilter()

    # ==========================================================================
    def load_water_body_station_filter(self):
        #        print('load_water_body_station_filter')
        self.water_body_station_filter = core.WaterBodyStationFilter(
            water_body_settings_directory=self.paths['directory_paths']['water_body_station_filter'],
            mapping_objects=self.mapping_objects)

    #==========================================================================
    def load_indicator_settings_filters(self): 
        """
        Updated:     20180419        by Lena Viktorsson
        Loads all types of settings, data and config files/objects. 
        """
        allowed_steps = ['step_2']
        if self.name not in allowed_steps:
            return False
        # All indicators in directory should be loaded automatically         
        # Load indicator setting files. Internal attr (_) since they are only used by other objects.  
        self._indicator_setting_files = {} 
        for indicator, file_path in self.paths['indicator_settings_paths'].items(): 
            self._indicator_setting_files[indicator] = core.SettingsFile(file_path, mapping_objects=self.mapping_objects)
            if self._indicator_setting_files[indicator].indicator != indicator:
                self._logger.debug('Missmatch in indicator name and object name! {}:{}'.format(self._indicator_setting_files[indicator].indicator, indicator))
                raise IndicatorFileError('Error in indicator settings file',
                                         'Missmatch in indicator name and object name! {}:{}'.format(self._indicator_setting_files[indicator].indicator, indicator))
                
        # Load Filter settings. Filter settings are using indicator_setting_files-objects as data
        self.indicator_data_filter_settings = {} 
        for indicator, obj in self._indicator_setting_files.items():
            self.indicator_data_filter_settings[indicator.lower()] = core.SettingsDataFilter(obj)
            
        # Load Ref settings. Filter settings are using indicator_setting_files-objects as data
        # TODO: this is doen twice why?
        self.indicator_ref_settings = {} 
        for indicator, obj in self._indicator_setting_files.items():
            self.indicator_ref_settings[indicator.lower()] = core.SettingsRef(obj) 
            
        # Load Tolerance settings. Filter settings are using indicator_setting_files-objects as data
        self.indicator_tolerance_settings = {} 
        for indicator, obj in self._indicator_setting_files.items():
            self.indicator_tolerance_settings[indicator.lower()] = core.SettingsTolerance(obj)
    
    #==========================================================================
    def get_results(self, force_loading_txt=False, **kwargs): 
        """
        Created 20180720    by Magnus 
        Updated 20180918    by Magnus
        Loads all files in the results-directory. 
        pkl-files are loaded by default if present. 
        Override this by setting force_loading_txt == True 
        Data is returned in a dictionary
        """
        #self.result_data = {}
        result_data = {}
        results_directory = self.paths.get('directory_paths', {}).get('results', None)
        if results_directory == None:
            raise exceptions.MissingPath
        
        if not os.path.exists(results_directory): 
            raise exceptions.MissingDirectory
        
        file_list = os.listdir(results_directory) 
        key_list = list(set([item.split('.')[0] for item in file_list]))
        
        save_load_object = core.SaveLoadDelete(results_directory)
        
        for key in key_list: 
            if kwargs.get('match_string') and kwargs.get('match_string') not in key:
                continue
            if kwargs.get('by'): 
                if 'by_' + kwargs.get('by') not in key:
                    continue
            df = save_load_object.load_df(key, load_txt=force_loading_txt)
            result_data[key] = df
            
        if not result_data: 
            exceptions.NoResultsInResultDirectory
        
        return result_data 
    
        
    #==========================================================================
    def set_indicator_settings_data_filter(self, indicator=None, filter_settings=None):
        """
        filter_settings are dicts like: 
            filter_settings[type_area][variable] = value 
        """
        if not self._change_ok(): 
            return 
        if filter_settings: 
            filter_object = self.indicator_data_filter_settings[indicator] 
            filter_object.set_values(filter_settings) 
        
    #==========================================================================
    def deprecated_save_indicator_settings(self, indicator): 
        if not self._change_ok(): 
            return 
        self.indicator_settings[indicator].save_file() # Overwrites existing file if no file_path is given
        return True 
    
    #==========================================================================
    def deprecated_save_all_indicator_settings(self): 
        if not self._change_ok(): 
            return 
        all_ok = True
        for obj in self.indicator_settings.values():
            if not obj.save_file() :
                all_ok = False
        return all_ok
        
    #==========================================================================
    def rename_paths(self, from_name, to_name, pre_directory=''): 
        """
        Replaces string in all file paths. 
        """
        for name in self.paths.keys(): 
            if type(self.paths[name]) == dict:
                for sub_name in self.paths[name].keys():
                    self.paths[name][sub_name] = get_new_path(from_name, to_name, self.paths[name][sub_name], pre_directory)
            else:
                self.paths[name] = get_new_path(from_name, to_name, self.paths[name], pre_directory) 
                
        # Rename paths in settings files 
        for indicator in self._indicator_setting_files.keys():
            self._indicator_setting_files[indicator].change_path(self.paths['indicator_settings_paths'][indicator]) 
            
        # Rename path in water_body_station_filter 
        self.water_body_station_filter.change_path(self.paths['directory_paths']['water_body_station_filter'])
            
    #==========================================================================
    def print_all_paths(self): 
        """
        Prints all path in the step.
        """
        sep_length = 100
        self._logger.debug('='*sep_length)
        self._logger.debug('='*sep_length)
        self._logger.debug('{} paths'.format(self.name))
        self._logger.debug('-'*sep_length)
        for item in sorted(self.paths.keys()):
            if type(self.paths[item]) == dict:
                for path in sorted(self.paths[item].keys()):
                    if type(self.paths[item][path]) == dict:
                        for p in sorted(self.paths[item][path].keys()):
                            self._logger.debug('-', self.paths[item][path][p])
                    else:
                        self._logger.debug(self.paths[item][path])
            else:
                self._logger.debug(self.paths[item])
                
        self._logger.debug('')
                
    #==========================================================================
    def set_data_filter(self, filter_type='', filter_name='', data=None, save_filter=True, append_items=False): 
        """
        Sets the data_filter. See core.filters.data_filter.set_filter for more information. 
        """ 
        if not self._change_ok(): 
            return 
        data_filter = self.get_data_filter_object() 
        data_filter.set_filter(filter_type=filter_type, 
                               filter_name=filter_name, 
                               data=data, 
                               save_filter=save_filter, 
                               append_items=append_items)    
        return True
    
    #==========================================================================
    def set_water_body_station_filter(self, water_body=None, include=True, station_list=None): 
        if include:
            self.water_body_station_filter.include_stations_in_water_body(station_list=station_list, water_body=water_body)
        else: 
            self.water_body_station_filter.exclude_stations_in_water_body(station_list=station_list, water_body=water_body)
            
    #==========================================================================
    def show_settings(self):
        self._logger.debug('first_filter:')
        self.data_filter.show_filter()
        
        
###############################################################################
class Subset(object):
    """
    Class to hold subset paths and objects. 
    """
    def __init__(self, 
                 alias=None, 
                 unique_id=None, 
                 parent_directory=None, 
                 mapping_objects={}, 
                 parent_workspace_object=None): 
        
        if not all([alias, unique_id, parent_directory]):
            raise exceptions.MissingInputVariable
        
        self.alias = alias 
        self.unique_id = unique_id
        self.paths = {}
        self.paths['parent_directory'] = parent_directory.replace('\\', '/')
        self.paths['subset_directory'] = '/'.join([self.paths['parent_directory'], self.unique_id]) 
        self.parent_workspace_object = parent_workspace_object
        self.paths['directory_path_log'] = self.parent_workspace_object.paths['directory_path_log']
        self.wb_id_header = self.parent_workspace_object.wb_id_header
        
        self.mapping_objects = mapping_objects
        
        self._initiate_attributes()
        self._load_steps() 
        
        # Add logger 
        if self.unique_id:
            self._set_logger(self.unique_id)
            self._set_loggers_to_steps()
        
        
    #==========================================================================
    def _initiate_attributes(self): 
        self.nr_steps = 5
        self.steps = {}
        self.available_indicators = []
            
        
    #==========================================================================
    def _set_logger(self, log_id):
        # Add logger 
        core.add_log(log_id=log_id, 
                     log_directory=self.paths['directory_path_log'], 
                     log_level='DEBUG', 
                     on_screen=True, 
                     prefix='subset')
        self._logger = core.get_log(log_id)
#        self._logger.debug('Logger set for subset {} with unique_id {}'.format(self. name, log_id))
    

    #==========================================================================
    def _set_loggers_to_steps(self): 
        for step in self.steps.keys():
            self.steps[step]._logger = self._logger
    
    
    #==========================================================================
    def _change_ok(self): 
        """
        Check to make sure that the default 
        """
        if self.parent_subset_object and self.parent_workspace_object.unique_id == 'default_workspace':
            self._logger.warning('Not allowed to change default workspace!')
            return False
        elif self.unique_id == 'default_subset':
            self._logger.warning('Not allowed to change default subset!')
            return False
        return True
    
    
    #==========================================================================
    def deprecated__load_subset_config(self): 
        self.config_object = Config(self.paths['subset_directory'] + '/subset.cfg')
        
        
    #==========================================================================
    def _load_steps(self): 
        if not os.path.exists(self.paths['subset_directory']): 
            os.makedirs(self.paths['subset_directory'])
            
        step_list = [item for item in os.listdir(self.paths['subset_directory']) if '.' not in item]
        for step in step_list:
            self._load_workstep(step)
        
        
    #==========================================================================
    def deprecated__add_files_from_subset(self, subset_object=None, overwrite=False):
        """
        Copy files from given subset. Option to overwrite or not. 
        This method is used to copy (branching) an entire subset. 
        """ 
        for step in subset_object.get_step_list(): 
            self._load_workstep(step)
            step_object = subset_object.get_step_object(step)
            self.steps[step].add_files_from_workstep(step_object=step_object, 
                                                     overwrite=overwrite)
            
        # Copy config file
        # This is done in Workspace since new uuid needs to be given
#        if os.path.exists(subset_object.config_file_path):
#            if os.path.exists(self.config_object_file_path) and not overwrite: 
#                return False 
#            
#            shutil.copy(subset_object.config_file_path, self.config_object_file_path)
#            self._load_config()
        return True
            
            
    #==========================================================================
    def _load_workstep(self, step=None): 
        step = get_step_name(step)
        if not step:
            return False
        
        self.steps[step] = WorkStep(name=str(step), 
                                    parent_directory=self.paths['subset_directory'], 
                                    mapping_objects=self.mapping_objects, 
                                    parent_workspace_object=self.parent_workspace_object, 
                                    parent_subset_object=self)
        return True
        
    #==========================================================================
    def deprecated_delete_workstep(self, step=None): 
        """
        step is like 'step_1', 'step_2' and so on. 
        """
        if step in self.subset_dict.keys(): 
            # TODO: Delete files and directories. How to make this safe? 
            self.steps.pop(step)
    
    #==========================================================================
    def deprecated_get_alias(self): 
        alias = self.config_object.get_config('alias') 
        if not alias:
            return '' 
        
    #==========================================================================
    def deprecated__set_unique_id(self): 
        """
        Sets a unique id (UUID) to the subset. Will not overwrite an existing one. 
        """
        self.unique_id = self.config_object.set_unique_id()  
        
    #==========================================================================
    def get_all_file_paths_in_subset(self): 
        """
        Returns a sorted list of all file paths in the subset tree. 
        """
        file_list = []
        for root, dirs, files in os.walk(self.paths['subset_directory']): 
                for f in files:
                    file_list.append('/'.join([root, f]).replace('\\', '/'))
        return sorted(file_list)

    #==========================================================================
    def get_data_filter_info(self, step): 
        """
        Returns a dict with information about the active filters. 
        """
        data_filter = self.get_data_filter_object(step)
        if not data_filter:
            return False
        return data_filter.get_data_filter_info()
    
    #==========================================================================
    def get_data_filter_object(self, step): 
        """
        Returns the data filter for the given step. 
        """
        step = get_step_name(step)
        if step not in self.get_step_list():
            return False 
        return self.steps[step].data_filter 
    
    #==========================================================================
    def get_step_list(self): 
        return sorted(self.steps.keys())
    
    #==========================================================================
    def get_step_object(self, step): 
        step = get_step_name(step)
        return self.steps.get(step, False)
        
    
    #==========================================================================
    def load_data(self, step): 
        if step not in self.steps.keys():
            self._logger.debug('Invalid step "{}" given to load data in subset "{}"!'.format(step, self.name))
            return False 
            
        self.steps[step].load_data()
                 
    #==========================================================================
    def deprecated_get_step_1_object(self): 
        return self.get_step_object('step_1')
    
    #==========================================================================
    def deprecated_get_step_2_object(self): 
        return self.get_step_object('step_2')
    
    #==========================================================================
    def deprecated_set_alias(self, alias):
        self._logger.debug('New alias for subset "{}" => "{}"'.format(self.config_object.get_config('alias'), alias))
        self.config_object.set_config('alias', alias)
        
    #==========================================================================
    def deprecated_rename_paths(self, from_name, to_name, pre_directory=''): 
        
        for name in self.paths.keys(): 
            if type(self.paths[name]) == dict:
                for sub_name in self.paths[name].keys():
                    self.paths[name][sub_name] = get_new_path(from_name, to_name, self.paths[name][sub_name], pre_directory)
            else:
                self.paths[name] = get_new_path(from_name, to_name, self.paths[name], pre_directory)


    #==========================================================================
    def deprecated_rename_subset(self, new_name): 
        if new_name.lower() in ['subset', 'default_subset']: 
            self._logger.debug('Invalid name "{}" for subset!'.format(new_name))
            return False 
        
        current_directory = self.paths['subset_directory']
        new_directory = '{}/{}'.format(self.paths['parent_directory'], new_name)
        
        # Rename all paths in subset 
        self.rename_paths(self.name, new_name, pre_directory='subsets')
        
        # Rename paths in steps 
        for step in self.steps.keys(): 
            self.steps[step].rename_paths(self.name, new_name, pre_directory='subsets') 
        
        # Rename directoy
        os.rename(current_directory, new_directory) 
        
        # Set path in config file 
        self.config_object.set_path(self.name, new_name, pre_directory='subsets')
        
        self.name = new_name
        
        return True 
    
    #==========================================================================
    def deprecated_rename_workspace(self, from_name, to_name): 
        
        # Rename all paths in subset 
        self.rename_paths(from_name, to_name, pre_directory='workspaces')
        
        # Rename paths in steps 
        for step in self.steps.keys(): 
            self.steps[step].rename_paths(from_name, to_name, pre_directory='workspaces')  
            
        # Set path in config file 
        self.config_object.set_path(from_name, to_name, pre_directory='workspaces')
        
        return True
            
    #==========================================================================
    def print_all_paths(self): 
        """
        Prints all path in the subset.
        """
        sep_length = 100
        self._logger.debug('='*sep_length)
        self._logger.debug('='*sep_length) 
        self._logger.debug('Subset {} paths'.format(self.name))
        self._logger.debug('-'*sep_length)
        for item in sorted(self.paths.keys()):
            if type(self.paths[item]) == dict:
                for path in sorted(self.paths[item].keys()):
                    if type(self.paths[item][path]) == dict:
                        for p in sorted(self.paths[item][path].keys()):
                            self._logger.debug('-', self.paths[item][path][p])
                    else:
                        self._logger.debug(self.paths[item][path])
            else:
                self._logger.debug(self.paths[item])
            
        for step in sorted(self.steps.keys()):
            self.steps[step].print_all_paths() 
        
        self._logger.debug('')
                
    #==========================================================================
    def set_data_filter(self, step='', filter_type='', filter_name='', data=None, save_filter=True, append_items=False):  
        step_object = self.get_step_object(step)
        if not step_object:
            return False 
        return step_object.set_data_filter(filter_type=filter_type, 
                                           filter_name=filter_name, 
                                           data=data, 
                                           save_filter=save_filter, 
                                           append_items=append_items)
    
    
    
            

###############################################################################
class WorkSpace(object):
    """
    Created     ????????    by Magnus Wenzer
    Updated     20180601    by Magnus Wenzer
        
    Class to hold and alter a workspace. 
    name is UUID. 
    """
    def __init__(self, 
                 alias=None, 
                 unique_id=None, 
                 parent_directory=None, 
                 resource_directory=None,
                 nr_subsets_allowed=4, 
                 mapping_objects=None, 
                 user_id=None): 
        
        if not all([alias, unique_id, parent_directory, user_id]):
            raise exceptions.MissingInputVariable
        if not nr_subsets_allowed:
            raise exceptions.MissingInputVariable
        

        # Initiate paths 
        self.paths = {}
        self.alias = alias 
        self.unique_id = unique_id
        self.user_id = user_id
        self.mapping_objects = mapping_objects
        self.wb_id_header = 'MS_CD'
        
        self.all_status = ['editable', 'readable', 'deleted']


        self.paths['parent_directory'] = parent_directory.replace('\\', '/')
        self.paths['resource_directory'] = resource_directory.replace('\\', '/')
        self.nr_subsets_allowed = nr_subsets_allowed 
        
        self._initiate_attributes()
        
        # Load UUID mapping file for subsets
        # 20180601 MW added user_id as argument
        self.uuid_mapping = core.UUIDmapping('{}/uuid_mapping.txt'.format(self.paths['directory_path_subset']), user_id=self.user_id)
        
        self._setup_workspace()
        
        # Add logger
        if self.unique_id: 
            self._set_logger(self.unique_id)
            self._set_loggers_to_steps()
        
        
        #self.deprecated_load_config_files() 
        
    #==========================================================================
    def _add_subset(self, unique_id=None): 
        assert unique_id, 'No subset name given!'
        
        if unique_id == 'default_subset':
            alias = 'default_subset' 
        else:
            alias = self.uuid_mapping.get_alias(unique_id)
        if unique_id in self.subset_dict.keys():
            self._logger.debug('Given subset "{}" with alias "{}" is already present!'.format(unique_id, alias))
            return False
        
        
        self.paths['directory_path_subsets'][unique_id] = self.paths['directory_path_subset'] + '/{}'.format(unique_id)

        self.subset_dict[unique_id] = Subset(alias=alias, 
                                             unique_id=unique_id, 
                                             parent_directory=self.paths['directory_path_subset'],
                                             mapping_objects=self.mapping_objects, 
                                             parent_workspace_object=self)
        return unique_id 
    
    
    #==========================================================================
    def _change_ok(self): 
        """
        Check to make sure that default workspace is not changed. 
        """
        if self.unique_id == 'default_workspace':
            self._logger.debug('Not allowed to change default workspace!')
            return False
        return True    
    
    
    #==========================================================================
    def _initiate_attributes(self): 
        
        # Setup default paths 
        self.paths['mapping_directory'] = '/'.join([self.paths['resource_directory'], 'mappings'])
        self.paths['workspace_directory'] = '/'.join([self.paths['parent_directory'], self.unique_id]) 
        
        self.paths['directory_path_subsets'] = {}
        self.paths['directory_path_input_data'] = self.paths['workspace_directory'] + '/input_data'
        self.paths['directory_path_raw_data'] = self.paths['directory_path_input_data'] + '/raw_data'
        self.paths['directory_path_export_data'] = self.paths['directory_path_input_data'] + '/exports'
        self.paths['directory_path_subset'] = self.paths['workspace_directory'] + '/subsets'
        self.paths['directory_path_log'] = self.paths['workspace_directory'] + '/log'
        self.paths['directory_path_cache'] = self.paths['workspace_directory'] + '/cache'
        
        # Create directories if not present 
        for key, p in self.paths.items():
            if type(p) == str:
                if not os.path.exists(p):
                    os.makedirs(p)
        # Step
        self.step_0 = None 
        
        # Subset 
        self.subset_dict = {} 
        
#        self.dtype_settings = core.RawDataFiles(self.paths['directory_path_raw_data'])
        
        self.datatype_settings = core.DataTypeMapping(self.paths['directory_path_input_data'])
        
        
    
    #==========================================================================
    def deprecated_load_config_files(self):       
        self.cf_df = pd.read_csv(self.paths['resource_directory'] + '/Quality_Elements.cfg', sep='\t', dtype='str', encoding='cp1252')
        assert all(['quality element' in self.cf_df.keys(), 'indicator' in self.cf_df.keys(), 'parameters' in self.cf_df.keys()]), 'configuration file must contain quality element, indicator and parameters information'
        self.cfg = {}
        self.cfg['quality elements'] = self.cf_df.groupby('quality element')['indicator'].unique()
        self.cfg['indicators'] = self.cf_df.groupby('indicator')['parameters'].unique()
#        for QE in self.cfg['quality elements']:
#            self.cfg[QE] = self.cf_df.groupby(QE)['indicator'].unique()
#        for indicator in self.cfg['indicators']:
#            self.cfg[indicator] = self.cf_df.groupby(QE)['parameters'].split(',') 


    #==========================================================================
    def _load_workstep(self, subset=None, step=None): 
        subset_object = self.get_subset_object(subset) 
        if not subset_object:
            return False 
        return subset_object._load_workstep(step)
    
    
    #==========================================================================
    def _set_logger(self, log_id):
        # Add logger 
        core.add_log(log_id=log_id, 
                     log_directory=self.paths['directory_path_log'], 
                     log_level='DEBUG', 
                     on_screen=True, 
                     prefix='workspace')
        self._logger = core.get_log(log_id)
#        self._logger.debug('Logger set for workspace {} with unique_id {}'.format(self. name, self.unique_id))
           

    #==========================================================================
    def _set_loggers_to_steps(self): 
        self.step_0._logger = self._logger
        for subset in self.subset_dict.keys():
            self.subset_dict[subset]._set_loggers_to_steps()
        
        
    #==========================================================================
    def _setup_workspace(self):
        """
        Adds paths and objects for the workspace. 
        """        
        # Create input data folder if non existing
#        if not os.path.exists(self.paths['directory_path_raw_data']):
#            os.makedirs(self.paths['directory_path_raw_data'])
#            
#        # Create raw data folder if non existing
#        if not os.path.exists(self.paths['directory_path_input_data']):
#            os.makedirs(self.paths['directory_path_input_data'])
#        
#        # Initiate one subset as default 
#        if not os.path.exists(self.paths['directory_path_subset']):
#            os.makedirs(self.paths['directory_path_subset'])
            
        subsets = [item for item in os.listdir(self.paths['directory_path_subset']) if '.' not in item]
#        self._logger.debug('subsets', subsets)
        if subsets:
            for s in subsets:
                self._add_subset(s)
        else:
            self._add_subset('default_subset')
            
        # Load config file 
#        self._load_workspace_config()
            
        # Step 0
        self.step_0 = WorkStep(name='step_0', 
                               parent_directory=self.paths['workspace_directory'], 
                               mapping_objects=self.mapping_objects, 
                               parent_workspace_object=self)
        
        # Set data and index handler
        self.data_handler = core.DataHandler(input_data_directory=self.paths['directory_path_input_data'], 
                                             resource_directory=self.paths['resource_directory'],
                                             mapping_objects=self.mapping_objects,
                                             wb_id_header=self.wb_id_header)
        
        self.index_handler = core.IndexHandler(workspace_object=self, 
                                               data_handler_object=self.data_handler)
        
        # Load Cache object    
        self.cache = core.Cache(self.paths['directory_path_cache'], mandatory_uuid=True, min_nr_arguments=3)
        

    #==========================================================================
    def import_file(self, file_path=None, data_type=None, status=0, force=True):
        """
        Created     ????????    by 
        Updated     20180721    by Magnus Wenzer
        
        Imports a data file to the raw_data directory in the workspace. 
        Also adds information to the datatype_settings-object.
        this method does not load data. 
        """ 
        
        assert all([file_path, data_type]), 'Not enough input arguments to import file' 
        
                   # Not able to load data into default workspace
        if not self._change_ok():
            print('1')
            return False
        
        if not os.path.exists(file_path): 
            print('2')
            return False 
        
        # Copy file
        target_file_path = '/'.join([self.paths['directory_path_raw_data'], os.path.basename(file_path)]) 
        if os.path.exists(target_file_path): 
            if force:
                os.remove(target_file_path)
            else:
                print('3')
                return False
        
        
        shutil.copyfile(file_path, target_file_path)
        
        # Add file to dtype_settings file
#        self.dtype_settings.add_file(file_path=file_path, data_type=data_type)
        self.datatype_settings.add_file(file_name=file_path, data_type=data_type, status=status)


    #==========================================================================
    def import_default_data(self, force=True):
        """
        Created     ????????    by Lena
        Updated     20180424    by Magnus Wenzer
        
        Imports default data from the resources directory to input raw_data directory in workspace.
        """
        # Not able to load data into default workspace
        if not self._change_ok():
            return False
        
        source_directory = self.paths['resource_directory'] + '/default_data'  
        
        file_name_list = os.listdir(source_directory)
        
        all_datatypes = [u'chlorophyll',
                         u'physicalchemical',
                         u'physicalchemicalmodel',
                         u'phytoplankton',
                         u'zoobenthos']
        
        # Copy files
        for file_name in file_name_list: 
            datatype = file_name.split('_')[0] 
            if datatype not in all_datatypes:
                continue
            source_file_path  = '/'.join([source_directory, file_name])
            self.import_file(file_path=source_file_path, data_type=datatype, force=force)
            self._logger.debug('Default data file has been copied to workspace raw data folder: {}'.format(file_name))
        
        # Have to load and sync to set status and loaded as int. Dont know why...
        self.datatype_settings.load_and_check_dtype_settings() 
        
#        # Load data 
#        self.load_all_data() 
#        self._logger.debug('Data has been loaded in import_default_data. flag "load_data" was set to True')
        
        # Update dtype_settings object
#        all_ok = self.dtype_settings.load_and_sync_dtype_settings()
#        all_ok = self.dtype_settings.load_and_check_dtype_settings()
#        all_ok = self.datatype_settings.load_and_check_dtype_settings()
#        
#        if not all_ok:
#            self._logger.warning('Default data not loaded correctly!')
#            return False
        return True
        
    #==========================================================================
    def set_status_for_file(self, file_list, status):
        """
        Created     20180424    by Magnus Wenzer
        Updated     20180424    by Magnus Wenzer
        """
        if status:
            status = 1 
        else:
            status = 0
        self.datatype_settings.set_status(file_list, status)
    
    
    #==========================================================================
    def apply_data_filter(self, step=None, subset=None, apply_all_previous_filters=True):
        """
        Created     20180608    by Magnus Wenzer
        Updated     
        
        Applies the data filter on the step given. 
        If apply_all_previous_filters==True all previous steps are applied before. 
        """
        if apply_all_previous_filters:
            step = get_step_name(step)
            step_nr = int(step[-1])
            
            for s in range(step_nr+1):
#                print('s', s)
#                self._apply_data_filter(step=s, subset=subset)
                if s==0:
                    self._apply_data_filter(step=s) # Cannot handle subset if step=0
                else:
                    self._apply_data_filter(step=s, subset=subset)
                
        else:
            self._apply_data_filter(step=step, subset=subset)
        

    #==========================================================================
    def _apply_data_filter(self, step=None, subset=None):
        """
        Created     ????????    by Magnus Wenzer
        Updated     20180220    by Magnus Wenzer
        
        
        Applies data filter to the index handler. 
        
        Input: 
            step:           step that the data filter should be applied on. 
                            data_filter can be applied on step 0, 1 and 2
                            
            subset:         subset to apply filter on. Must be provided if step is > 0 
        
        Output: 
            True:           If all is ok
            False:          If something faild
        """
        
        step = get_step_name(step)
        if step == 'step_0':
            filter_object = self.step_0.data_filter
            
        elif int(step[-1]) > 2: 
            self._logger.debug('No data filter in {}'.format(step))
            return False
        
        elif subset not in self.get_subset_list(): 
            self._logger.debug('Provides subset "{}" not in subset list'.format(subset))
            return False
        else:
            subset_object = self.get_subset_object(subset) 
            step_object = subset_object.get_step_object(step)
            filter_object = step_object.get_data_filter_object() 
            
        all_ok = self.index_handler.add_filter(filter_object=filter_object, step=step, subset=subset)
        return all_ok
        
    
    #==========================================================================
    def apply_indicator_data_filter(self, subset='', indicator='', step='step_2', water_body_list = False):
        """
        Created     ????????    by Magnus Wenzer
        Updated     20180719    by Magnus Wenzer
        
        Applies indicator data filter to the index handler. Step 2. Applies filter for all water_bodies. 
        
        Input:                
            subset:         subset to apply filter on. 
            
            indicator:      name of indicator to apply as a string, ex. "din_winter" 
            
            step:           step_2 is default
        
        Output: 
            True:           If all is ok
            False:          If something faild
        """
        t_tot = time.time()
        if not water_body_list:
            water_body_list = self.get_filtered_data(step='step_1', subset=subset)[self.wb_id_header].unique()
        if not len(water_body_list):
            #raise Error?
            self._logger.warning('No waterbodies in filtered data')
            return False
        
        if subset not in self.get_subset_list(): 
            self._logger.debug('Provided subset "{}" not in subset list'.format(subset))
            return False
        
        # Find first year of filtered data from step 1. 
        kwargs = {}
        df = self.get_filtered_data(subset=subset, step=1)
        kwargs['remove_data_before_year'] = min(df['MYEAR'])
        
        # Get subset and step objects
        step_nr = step
        step = get_step_name(step)
        subset_object = self.get_subset_object(subset) 
        # Indicator_settings are linked to step 2 by default
        step_object = subset_object.get_step_object(step) 
        step_object.load_water_body_filter_object()
        # Get filter objects
        water_body_filter_object = step_object.get_water_body_filter_object()
        water_body_station_filter_object = step_object.get_water_body_station_filter_object()
        indicator = indicator.lower()
        settings_filter_object = step_object.get_indicator_data_filter_settings(indicator)
        if step not in self.index_handler.booleans['step_0'][subset]['step_1'].keys():
            # If step_2 filter has not been added, add this now.
            self.apply_data_filter(step=step_nr, subset=subset)
            # self.index_handler.add_filter(filter_object=water_body_filter_object, step=step, subset=subset, **kwargs)
            # TODO: should water_body be None above and should this not be moved outside the water_body loop?
            # Also it is wrong that the filter object here is water_body_filter_object

        #set filters for all indicator in all waterbodies and if no key in boolean dict for waterbody add waterbody filter
        for water_body in dict.fromkeys(water_body_list, True):
            type_area = self.mapping_objects['water_body'].get_type_area_for_water_body(water_body, include_suffix=True)
            if type_area == '':
                continue
            if water_body not in self.index_handler.booleans['step_0'][subset]['step_1']['step_2'].keys():
            # If a filter for the waterbody has not been added, add this now
                if bool(water_body_station_filter_object.get_list(water_body=water_body)) | \
                        bool(water_body_station_filter_object.get_list(include=False, water_body=water_body)):
                    # station filter for waterbody
                    self.apply_water_body_station_filter(subset=subset, water_body=water_body, **kwargs)
                else:
                    # no station filter for waterbody
                    self.apply_water_body_filter(subset=subset, water_body=water_body, **kwargs)

                    # self.index_handler.add_filter(filter_object=water_body_filter_object, step=step, subset=subset,
                    #                               water_body=water_body, **kwargs)
            # index_handler should have filters for step and waterbody, now add filter for the indicator from
            # the filter object for settings
            self.index_handler.add_filter(filter_object=settings_filter_object, step=step, subset=subset,
                                          indicator=indicator, water_body=water_body, **kwargs)
            temp_df_1 = self.get_filtered_data(step=2, subset=subset, water_body=water_body)
            temp_df_2 = self.get_filtered_data(step=2, subset=subset, indicator=indicator, water_body=water_body)
            if len(temp_df_2['WATER_BODY_NAME'].unique()) > 1:
                print('waterbodies after station filter and {} filter {}'.format(indicator, temp_df_2['WATER_BODY_NAME'].unique()))
                print('statn after filters {}'.format(temp_df_2['STATN'].unique()))
                print('-'*50)
            # print(temp_df_2['WATER_BODY_NAME'].unique(), temp_df_2['STATN'].unique())
        time_total = time.time() - t_tot
        print('-'*50)
        print('Total time to apply data filters for indicator {}:'.format(indicator), time_total)
        print('-'*50)

    # ==========================================================================
    def apply_water_body_filter(self, subset=None, water_body=None, **kwargs):
        """
        set boolean for waterbody key in boolean dict. Should look in all relevant filterobjects for the waterbody
        filterobjects currently used: WaterBodyFilter, WaterBodyStationFilter
        use or between filters to get boolean
        :param subset:
        :param waterbody:
        :return: no return
        """
        step = 2
        if subset not in self.get_subset_list():
            self._logger.debug('Provides subset "{}" not in subset list'.format(subset))
            return False
        else:
            # Get subset and step objects
            step = get_step_name(step)
            subset_object = self.get_subset_object(subset)
            step_object = subset_object.get_step_object(step)
            # Get filter objects
            water_body_filter_object = step_object.get_water_body_filter_object()

        all_ok = self.index_handler.add_filter(filter_object=water_body_filter_object, step=step,
                                               subset=subset, water_body=water_body, **kwargs)
        return all_ok


    # ==========================================================================
    def apply_water_body_station_filter(self, subset=None, water_body=None, **kwargs):
        """
        Filter is applied in step 2. 
        """
        step = 2
        if subset not in self.get_subset_list(): 
            self._logger.debug('Provided subset "{}" not in subset list'.format(subset))
            return False
        else:
            step = get_step_name(step)
            subset_object = self.get_subset_object(subset) 
            # Indicator_settings are linked to step 2 by default
            step_object = subset_object.get_step_object(step) 
            filter_object = step_object.get_water_body_station_filter_object()

        all_ok = self.index_handler.add_filter(filter_object=filter_object, step=step,
                                               subset=subset, water_body=water_body, **kwargs)
        temp_df = self.get_filtered_data(step=2, subset=subset)
        temp_df = self.get_filtered_data(step=2, subset=subset, water_body=water_body)
        return all_ok
        
        
    #==========================================================================
    def copy_subset(self, source_uuid=None, target_alias=None):
        """
        Created     20180219    by Magnus Wenzer
        Updated     20180601    by Magnus Wenzer
        
        Creates a copy of a subset. 
        """
        assert all([source_uuid, target_alias])
        
        if not source_uuid:
            self._logger.warning('No subset named "{}"'.format(source_uuid))
            raise exceptions.SubsetNotFound
#            return False
        
        # Add UUID for workspace in uuid_mapping 
        target_uuid = self.uuid_mapping.add_new_uuid_for_alias(target_alias)
        if not target_uuid:
            self._logger.debug('Could not add subset with alias "{}". Subset already exists!'.format(target_alias)) 
            raise exceptions.SubsetAlreadyExists
#            return False

        # Copy all directories and files in subset 
        source_subset_path = '/'.join([self.paths['directory_path_subset'], source_uuid])
        target_subset_path = '/'.join([self.paths['directory_path_subset'], target_uuid]) 
        
        
#        print('source_subset_path:', source_subset_path)
#        print('target_subset_path:', target_subset_path)
        
        # Copy files
        shutil.copytree(source_subset_path, target_subset_path)
        
        
        # Load subset 
        self._add_subset(target_uuid)
        
        target_status = self.uuid_mapping.get_status(unique_id=target_uuid) # Check in case default is changed
        
        return {'alias': target_alias, 
                'subset_uuid': target_uuid, # MW: 20180524
                'status': target_status}
    
    #==========================================================================
    def request_subset_list(self):
        # TODO: update this! 
        """
        Created     20180219    by Magnus Wenzer
        Updated     20180219    by Magnus Wenzer 
        
        Returns a list with dicts with keys: 
            alias 
            uid 
            status
        Information is taken from uuid_mapping. No data has to be loaded. 
        """
        return_list = [] 
        for alias in self.uuid_mapping.get_alias_list_for_user(self.user_id, status=self.all_status):
            return_list.append({'alias': alias, 
                                'uuid': self.uuid_mapping.get_uuid(alias, self.user_id, self.all_status),
                                'status': self.uuid_mapping.get_status(alias, self.user_id)})
        return return_list
        
        
    #==========================================================================
    def print_all_paths(self): 
        """
        Prints all path in the workspace.
        """
        sep_length = 100
        self._logger.debug('='*sep_length)
        self._logger.debug('='*sep_length)
        self._logger.debug('Workspace root paths')
        self._logger.debug('-'*sep_length)
        for item in sorted(self.paths.keys()):
            if type(self.paths[item]) == dict:
                for path in sorted(self.paths[item].keys()):
                    if type(self.paths[item][path]) == dict:
                        for p in sorted(self.paths[item][path].keys()):
                            self._logger.debug('-', self.paths[item][path][p])
                    else:
                        self._logger.debug(self.paths[item][path])
            else:
                self._logger.debug(self.paths[item])
                
        self.step_0.print_all_paths()
        
        for subset in sorted(self.subset_dict.keys()):
            self.subset_dict[subset].print_all_paths()
        
        self._logger.debug('')
        
    #==========================================================================
    def data_is_loaded(self):
        """
        Created     20180720    by Magnus Wenzer
        Updated    
        
        Returns True if data is loaded else return False. 
        """
        if len(self.data_handler.all_data):
            return True
        else:
            return False
        
        
    #==========================================================================
    def data_is_available(self):
        """
        Created     20180720    by Magnus Wenzer
        Updated    
        
        Returns True if data is available else return False. 
        """
        return self.datatype_settings.has_data() 
        
        
        
    #==========================================================================
    def delete_all_export_data(self):
        """
        Created     20180423    by Magnus Wenzer
        Updated     20180423    by Magnus Wenzer
        
        Permanently deletes all files in the data export directory. 
        Also sets column "loaded" in datatype_settings.txt to 0. 
        """
        for file_name in os.listdir(self.paths['directory_path_export_data']): 
            file_path = '/'.join([self.paths['directory_path_export_data'], file_name])
            os.remove(file_path)
        
        # Reset loaded in datatype_settings 
        self.datatype_settings.reset_loaded()
        self._logger.debug('All files in export directory are deleted and all "loaded" in datatype_settings is 0.')
        
        
    #==========================================================================
    def delete_alldata_export(self):
        """
        Created     20180411    by Lena Viktorsson
        Updated     20180525    by Magnus
        
        Permanently deletes all_data.txt and all_data.pickle. 
        """
        
        sld_object = core.SaveLoadDelete(self.paths['directory_path_export_data'])
        sld_object.delete_files('all_data')
#        sld_object.delete_files('all_data_raw')
        
#        try:
#            os.remove(self.paths['directory_path_input_data'] + '/exports/all_data.txt')
#            self._logger.debug('all_data.txt deleted')
#        except OSError:
#            pass
#        try:
#            os.remove(self.paths['directory_path_input_data'] + '/exports/all_data.pickle')
#            self._logger.debug('all_data.pickle deleted')
#        except OSError:
#            pass
        
        
    #==========================================================================
    def delete_datatype_export(self, datatype):
        """
        Created:        20180422    by Magnus Wenzer 
        Last modified:  20180422    by Magnus Wenzer   
        
        Permanently deletes the raw_format and column_format data files for the given datatype. 
        """
        
        try:
            file_name = 'column_format_{}_data.txt'.format(datatype)
            os.remove('{}/{}'.format(self.paths['directory_path_export_data'], file_name))
            self._logger.debug('{} deleted'.format(file_name))
        except OSError:
            pass
        try:
            file_name = 'column_format_{}_data.pickle'.format(datatype)
            os.remove('{}/{}'.format(self.paths['directory_path_export_data'], file_name))
            self._logger.debug('{} deleted'.format(file_name))
        except OSError:
            pass
        
        try:
            file_name = 'raw_format_{}_data.txt'.format(datatype)
            os.remove('{}/{}'.format(self.paths['directory_path_export_data'], file_name))
            self._logger.debug('{} deleted'.format(file_name))
        except OSError:
            pass
        
        
    #==========================================================================
    def delete_subset(self, alias=None, unique_id=None, permanently=False): 
        """
        Created     20180219    by Magnus Wenzer
        Updated     20180219    by Magnus Wenzer
        
        Permanently deletes the given subset. 
        """
        if alias:
            unique_id = self.uuid_mapping.get_uuid(alias=alias, user_id=self.user_id)
        else:
            alias = self.uuid_mapping.get_alias(unique_id=unique_id)
        
#        if unique_id not in self.subset_dict.keys(): 
#            self._logger.warning('Subset "{}" with alias "{}" does not exist!'.format(unique_id, alias))
#            return False 

        if permanently:
            path_to_remove = self.paths['directory_path_subsets'].get(unique_id)
            if not ('workspace' in path_to_remove) & ('subset' in path_to_remove):
                self._logger.error('Trying to remove subset but the path to delete is not secure!') 
                return False
            
            self._logger.warning('Permanently deleting subset "{}" with alias "{}".'.format(unique_id, alias))
            # Delete files and folders: 
            shutil.rmtree(path_to_remove)
            
            # Remove objects and links 
            if unique_id in self.subset_dict.keys():
                self.subset_dict.pop(unique_id)
                self.paths['directory_path_subsets'].pop(unique_id) 
            
            # Remove in uuid_mapping
            self.uuid_mapping.permanent_delete_uuid(unique_id) 
        else:
            self._logger.warning('Removing subset "{}" with alias "{}".'.format(unique_id, alias)) 
            self.uuid_mapping.set_status(unique_id, 'deleted')
            self.uuid_mapping.set_inactive(unique_id)
        
        return True
            
    
    #==========================================================================
    def get_all_file_paths_in_workspace(self): 
        """
        Returns a sorted list of all file paths in the workspace tree. 
        """
        file_list = []
        for root, dirs, files in os.walk(self.paths['workspace_directory']): 
                for f in files:
                    file_list.append('/'.join([root, f]).replace('\\', '/'))
        return sorted(file_list)
    
    
    #==========================================================================
    def get_all_file_paths_in_input_data(self):
        file_list = []
        for root, dirs, files in os.walk(self.paths['directory_path_input_data']): 
                for f in files:
                    file_list.append('/'.join([root, f]).replace('\\', '/'))
        return sorted(file_list)
    
    
    #==========================================================================
    def get_alias_for_unique_id(self, unique_id):
        return self.uuid_mapping.get_alias(unique_id=unique_id)
    
    
    #==========================================================================
    def get_unique_id_for_alias(self, alias):
        return self.uuid_mapping.get_uuid(alias)
        
    
    #==========================================================================
    def get_data_filter_object(self, step=None, subset=None): 
        step_object = self.get_step_object(step=step, subset=subset)
        if not step_object:
            return False
        return step_object.get_data_filter_object()
    
    
    #==========================================================================
    def get_water_body_station_filter_object(self, subset=None):
        step = 2
        step_object = self.get_step_object(step=step, subset=subset)
        if not step_object:
            return False
        return step_object.get_water_body_station_filter()
        
    
    #==========================================================================
    def get_data_filter_info(self, step=None, subset=None): 
        data_filter = self.get_data_filter_object(step=step, subset=subset)
        if not data_filter:
            return False
        return data_filter.get_filter_info()
    
    def get_data_for_waterstool(self, step=None, subset=None):
        
        if step != 3:
            return False
        step_object = self.get_step_object(step = step, subset = subset)
        result_directory = step_object.paths['step_directory']+'/output/results/'
        
        indicator_filelist = [f for f in os.listdir(result_directory) if '-by_date.pkl' in f]
        sld = core.SaveLoadDelete(result_directory) 
        indicator_dict = {}
        datatype_dict = {'physchem': [], 'phytoplankton': [], 'chlorophyll': [], 'zoobenthos': []}
        # TODO put this in config file
        indicator2datatype = {'ntot_winter': 'physchem', 'ptot_winter': 'physchem',
                              'din_winter': 'physchem', 'dip_winter': 'physchem',
                              'ntot_summer': 'physchem', 'ptot_summer': 'physchem',
                              'secchi': 'physchem', 'oxygen': 'physchem',
                              'biov': 'phytoplankton', 'chl': 'chlorophyll',
                              'bqi': 'zoobenthos'}
        for indicator in indicator_filelist:
#             if not os.path.exists(sld.directory + indicator + '-by_date.pkl') or not os.path.exists(sld.directory +indicator + '-by_date.txt'):
#                 pass #self.indicator_dict[indicator] = False
#             else:
            datatype = indicator2datatype[indicator.split('-')[0][10:]]
            datatype_dict[datatype].append(sld.load_df(file_name = indicator))
            indicator_dict[indicator] = sld.load_df(file_name = indicator) # + '-by_date'
        column_mapping = pd.read_csv(self.paths['resource_directory'] + '/mappings/waters_column_mapping.txt',
                                     sep='\t', encoding='cp1252')
        c = {key: value[0] for key, value in column_mapping.to_dict('list').items()}
        remove_cols = ['REFERENCE_VALUE', 'HG_VALUE_LIMIT', 'GM_VALUE_LIMIT', 'MP_VALUE_LIMIT', 'PB_VALUE_LIMIT',
                       'global_EQR', 'local_EQR']
        for key, item in datatype_dict.items():
            df_list = item
            df = pd.concat(df_list)
            df = df.rename(columns=c)
            col_list = df.columns
            col_list = [c for c in col_list if c not in remove_cols]
            sld.save_df(df[col_list], 'WATERS_export_'+key, force_save_txt=True)

        df_list = list(indicator_dict.values())
        all_df = pd.concat(df_list)
        column_mapping = pd.read_csv(self.paths['resource_directory'] + '/mappings/waters_column_mapping.txt', sep='\t', encoding='cp1252')
        c = {key: value[0] for key, value in column_mapping.to_dict('list').items()}
        all_df = all_df.rename(columns=c)
        
        col_list = all_df.columns
        remove_cols = ['STATUS', 'REFERENCE_VALUE', 'HG_VALUE_LIMIT', 'GM_VALUE_LIMIT', 'MP_VALUE_LIMIT', 'PB_VALUE_LIMIT',
                       'global_EQR', 'local_EQR', 'POSITION', 'index_column', 'new_index', 'B']
        col_list = [c for c in col_list if not c in remove_cols]
        test = all_df[col_list]
        print(test.columns)

        sld.save_df(all_df[col_list], 'WATERS_export', force_save_txt=True)
        
    #==========================================================================
    def get_filtered_data(self, step=None, subset=None, water_body=None, indicator=None): 
        """
        Returns filtered data using the given filter level. 
        """
        step = get_step_name(step)
        if step == None:
            return False
#        self._logger.debug('STEP: {}'.format(step))
        return self.index_handler.get_filtered_data(subset=subset, step=step, water_body=water_body, indicator=indicator)
    
    
    #==========================================================================
    def get_available_indicators(self, subset=None, step=None):
        """
        Created:        201801   by Lena
        Last modified:  20180718 by Magnus
        """
        #TODO: nu kollar den bara om det finns fler än 0 rader med givna parameters för indikatorn, kanske öka den gräns?
        try:
            self.data_handler.all_data
        except AttributeError as e:
            #TODO: lägga till felmeddelande i log?
            print(e)
            return False
        
        available_indicators = []
        filtered_data = self.get_filtered_data(step=step, subset=subset) # MW 20180718 Moved here
        if len(filtered_data): # 20180611, MW added if, LV 20181012 moved outside loop
            #for indicator, parameters in self.cfg['indicators'].items():
            for indicator, row in self.mapping_objects['quality_element'].indicator_config.iterrows():
                parameter_list = [item.strip() for item in row['parameters'].split(', ')]
                if 'indicator' in parameter_list[0] or 'qe' in parameter_list[0]:
                    continue
                #parameter_list = [item.strip() for item in parameters[0].split(', ')]
    #            print('subset', subset)
                try:
                    #TODO: speed of pd.to_numeric? is pd.to_numeric really needed?
                    if indicator == 'indicator_chl': 
                        if parameter_list[0] in filtered_data.columns:
                            if len(filtered_data.dropna(subset = [parameter_list[0]])) > 0:
                                available_indicators.append(indicator)
                        elif parameter_list[1] in filtered_data.columns:
                            if len(filtered_data.dropna(subset = [parameter_list[1]])) > 0:
                                available_indicators.append(indicator)
                    elif 'sat' in indicator:
                        if len(filtered_data.dropna(subset = [parameter_list[0]])) > 0: # LV 20181126 
                            available_indicators.append(indicator)
                    else:
                        filtered_data[parameter_list].apply(pd.to_numeric).dropna(thresh = len(parameter_list)) # MW 20180718
                        available_indicators.append(indicator)
                except KeyError as e:
                    #TODO: lägga till felmeddelande i log?
    #                print('7777777', indicator)
    #                print(e)
                    print('{} not in filtered_data'.format(parameter_list))
                    pass

        
        self.available_indicators = available_indicators            
        return available_indicators


    #==========================================================================
    def get_indicator(self, subset = None, indicator = None):  
        """
        Created:        20180326     by Lena
        Last modified:  20180326     by Lena
        create dict containing indicator objects according to data availability or choice?
        This should be moved to WorkStep class, and should be run accesed only for step 3.
        """
        step_object = self.get_step_object(step = 3, subset = subset)
        return step_object.indicator_objects.get(indicator, False)
        
    
    #==========================================================================
    def get_indicator_settings_data_filter_object(self, subset=None, step='step_2', indicator=None): 
        step_object = self.get_step_object(subset=subset, step=step)
        return step_object.get_indicator_data_filter_settings(indicator)
    
    
    #==========================================================================
    def get_indicator_settings_name_list(self, subset=None, step=2):
        step_object = self.get_step_object(subset=subset, step=step)
        return sorted(step_object.indicator_settings.keys())
    
    
    #==========================================================================
    def get_subset_list(self):
        """
        Used
        """
        return sorted(self.subset_dict.keys())
    
    
    #==========================================================================
    def get_subset_object(self, subset): 
        return self.subset_dict.get(subset, False)
    
    
    #==========================================================================
    def get_step_object(self, step=None, subset=None): 
        step = get_step_name(step)
        if step == 'step_0':
            return self.step_0
        
        if not all([subset, step]):
            raise exceptions.MissingInputVariable
        
        sub = self.get_subset_object(subset)
        if not sub:
            return False
        return sub.get_step_object(step)
    
    
    #==========================================================================
    def get_step_0_object(self): 
        return self.step_0 
    
    
    #==========================================================================
    def get_step_1_object(self, subset): 
        return self.subset_dict[subset].get_step_1_object()
    
    
    #==========================================================================
    def get_step_2_object(self, subset): 
        return self.subset_dict[subset].get_step_2_object()
    
    
    #==========================================================================
    def initiate_quality_factors(self, ):
        return False
        
    #==========================================================================
    def load_all_data(self, force=False): 
        """ 
        Created:        2017        by Johannes Johansson (?)
        Last modified:  20180721    by Magnus Wenzer
        
        Loads all data from the input_data/raw_data-directory belonging to the workspace. 
        Only loads data if any file in dtype_settings in set to not "loaded" (loaded=0)
        """
#        output_directory = self.paths['directory_path_export_data'] 
        """
        # The input_data directory is given to DataHandler during initation. 
        # If no directory is given use the default directory! 
        # This has to be done in physicalchemical, zoobenthos etc. 
        """
        if force: 
            self._logger.debug('Method load_all_data is forced.')
            # method is forced so we delete all_data (if existing)
            self.delete_all_export_data()
        elif not self.datatype_settings.has_info:
            self._logger.debug('Could not load datatype_settings.txt. No file found?')
            return False
            
        if self.datatype_settings.no_data_to_load():
#            print('self.datatype_settings.no_data_to_load():')
            self._logger.debug('No data to load.')
            self.delete_all_export_data() 
            return True
            
        elif not self.datatype_settings.all_data_is_loaded(): 
#            print('self.datatype_settings.all_data_is_loaded():')
            self._logger.debug('All selected data in (status 1 in datatype_settings.txt) is not loaded.')
            # dtype_settings is not matching the loaded files so we delete all_data (if excisting)
            self.delete_alldata_export()

        if os.path.isfile(self.paths['directory_path_export_data'] + '/all_data.txt'): 
            # Data file excist. Try to load it, or pickle if existing
            data_loaded, filetype = self.data_handler.load_all_datatxt()
            if data_loaded:
                self._logger.debug('Data has been loaded from existing all_data.{} file.'.format(filetype))
            else:
                self._logger.debug("""all_data.txt already loaded and datatype_settings.txt is unchanged. 
                                   Call "delete_alldata_export" and load data again to reload all_data""") 
                data_loaded = True
        else:
#            print('load_all_data - else')
            # We know that all_data does not excist. We only want to load the datatypes that has been changed and then merge data. 
            # Loop and load datatypes (if loaded are decided in method load datatype_data)
            for datatype in self.datatype_settings.get_datatype_list():
#                print('-- datatype', datatype)
#                print('-- force', force)
                self.load_datatype_data(datatype=datatype, force=force) 
            try: 
                self.data_handler.merge_all_data(save_to_txt=False) 
            except exceptions.MissingKeyInData as e:
                file_name = e.message.split(':')[-1].strip()
                self.datatype_settings.set_key(file_name=file_name, key='status', value=0)
                self.datatype_settings.set_key(file_name=file_name, key='loaded', value=0)
                raise exceptions.MissingKeyInData
            data_loaded = True
            
        if not len(self.data_handler.all_data):
            raise exceptions.UnableToLoadData(message='No data is loaded!', 
                                              code='no_data_loaded')
            
        return data_loaded
        
    
    #==========================================================================
    def load_datatype_data(self, datatype=False, force=False): 
        """ 
        Created:        20180422    by Magnus Wenzer 
        Last modified:  20180422    by Magnus Wenzer 
        
        Load data for the specific datatype. 
        """ 
#        print('¤'*50)
#        print('load_datatype_data'.upper())
#        print(self.datatype_settings.get_file_paths_to_load_for_datatype(datatype, force=False, reload_file=True))
#        print(self.datatype_settings.df)
#        print('&'*50)
        if not self.datatype_settings.all_selected_files_loaded_for_datatypes(datatype): 
#            print('if not self.datatype_settings.all_selected_files_loaded_for_datatypes(datatype):')
            self.delete_datatype_export(datatype)
            
        elif force: 
            self.delete_datatype_export(datatype) 


        output_file_name = 'column_format_{}_data.pickle'.format(datatype)
        output_file_path = '/'.join([self.paths['directory_path_export_data'], output_file_name])
        if os.path.isfile(output_file_path):
#            print('1')
            # Data file excist. Try to load it, or pickle if excisting
            data_loaded = self.data_handler.load_datatypetxt(datatype)
            if data_loaded:
#                print('2')
                self._logger.debug('Data has been loaded from existing file: {}'.format(output_file_name))
        else: 
            # No datafile excist. 
            datatype_handler_object = getattr(self.data_handler, datatype) 
            
            # Delete sources 
            for source in self.datatype_settings.get_file_paths_to_delete_for_datatype(datatype, reload_file=True):
                datatype_handler_object.delete_source(source) 
                
            # Add sources 
#            print(datatype)
            for source in self.datatype_settings.get_file_paths_to_load_for_datatype(datatype, force=False, reload_file=True): 
#                print('SOURCE', source)
                datatype_handler_object.load_source(file_path=source, raw_data_copy=True) 
                self.datatype_settings.set_file_is_loaded(os.path.basename(source))
            
            datatype_handler_object.save_column_data(output_file_path) 
            self._logger.debug('New data files has been loaded for datatype: {}'.format(datatype))
    
    
    #==========================================================================
    def reset_data_filter(self, subset_uuid=None, step=1, include_filters=[], exclude_filters=[]): 
        """
        Created 20180608    by Magnus Wenzer 
        Updated 
        
        Resets the data filter in include_filters and exclude_filters. 
        If arguments=True all filters in group are reset. 
        """ 
        data_filter_object = self.get_data_filter_object(step=step, subset=subset_uuid)
        data_filter_object.reset_filter(include_filters=include_filters, 
                                        exclude_filters=exclude_filters)
        
        
        
    #==========================================================================
    def set_data_filter(self, step='', subset='', filter_type='', filter_name='', data=None, save_filter=True, append_items=False): 
        """
        Sets/changes the data_filter of the given filter_name. 
        
        Input: 
            step:           Specify in what step you want to change the data filter. 
                            data_filter can be applied on step 0, 1 and 2
                            
            subset:         Subset that the step belog to. Must be provided if step is > 0 
            
            filter_type:    Can be "include_list" or "exclude_list"
            
            filter_name:    Name of filter that you want to change. 
                            Name follows the CodeList
            
            data:           value that you want to change to
            
            save filter:    option to save text file. default is true
        """
        
        assert filter_type in ['include_list', 'exclude_list'], 'filter_type must be include_list or exclude_list'
        if not self._change_ok():
            return False
        
        step = get_step_name(step)
        step_object = self.get_step_object(step=step, subset=subset)
        if not step_object:
            return False
        if int(step[-1]) > 2:
            self._logger.warning('Data filter can only be applied on step_2 or lower!')
            return False
        return step_object.set_data_filter(filter_type=filter_type, 
                                            filter_name=filter_name, 
                                            data=data, 
                                            save_filter=save_filter, 
                                            append_items=append_items)
        
        
    #==========================================================================
    def set_indicator_settings_data_filter(self, indicator=None, filter_settings=None, subset=None, step=2): 
        """
        Sets/changes the indicator_settings_data_filter of the given indicator. 
        filter_settings is a dict like: 
            filter_settings[type_area][variable] = value
        
        Input: 
            indicator:          Indicator that you want to change settings for. 
                            
            filter_settings:    values in a dict like: filter_settings[type_area][variable]
                                If variable is 
            
            subset:             Subset that you want to change the indicator settings for. 
            
            step:               Default is 2
            
        """
        step_object = self.get_step_object(step=step, subset=subset)
        if not step_object:
            return False
        return step_object.set_indicator_settings_data_filter(indicator=indicator, 
                                                              filter_settings=filter_settings)

    #==========================================================================
    def set_water_body_station_filter(self, subset='', water_body=None, include=True, station_list=None): 
        """
        Sets/changes the data_filter of the given filter_name. 
        
        Input:               
            subset:         Subset that the step belog to
            
            water_body:     water body to apply filter on
            
            include:        True = include
                            False = exclude
            
            station_list:   list of stations
            
            step:           Default is 2 (moved outside/below)
        """
        step = 2
        if not self._change_ok():
            return False
        
        step = get_step_name(step)
        step_object = self.get_step_object(step=step, subset=subset)
        if not step_object:
            return False

        return step_object.set_water_body_station_filter(water_body=water_body, 
                                                         include=include, 
                                                         station_list=station_list)
    
    #==========================================================================
    def deprecated_get_unique_id(self): 
        return self.config_object.get_unique_id()
    

    #==========================================================================
    def deprecated_load_workspace_config(self): 
        self.config_object = Config(self.paths['workspace_directory'] + '/workspace.cfg')   
    
    #==========================================================================
    def deprecated_save_indicator_settings(self, indicator=None, subset=None): 
        """
        Saving indicator settings is only possible in step 2. 
        """
        # TODO: Chould later steps be removed if indicator settings are saved (saving only possible at level 2)?
        if not self._change_ok(): 
            return 
        step_object = self.get_step_2_object(subset)
        step_object.indicator_settings[indicator].save_file() # Overwrites existing file if no file_path is given
        return True 
    
    #==========================================================================
    def deprecated_save_all_indicator_settings_in_subset(self, subset): 
        if not self._change_ok(): 
            return 
        all_ok = True
        step_object = self.get_step_2_object(subset)
        for obj in step_object.indicator_settings.values():
            if not obj.save_file():
                all_ok = False
        return all_ok 
    
    #==========================================================================
    def deprecated_copy_subset(self, source_subset_name=None, target_subset_name=None): 
        assert all([source_subset_name, target_subset_name])
        if not self._add_subset(sub=target_subset_name):
            return False
        all_ok = self.subset_dict[target_subset_name]._add_files_from_subset(self.subset_dict[source_subset_name], overwrite=True) 
        if not all_ok:
            return all_ok
        
        # Copy subset.cfg. This will give the new subset a new uuid 
        des_path = self.subset_dict[target_subset_name].config_object.file_path
        self.subset_dict[target_subset_name].config_object = self.subset_dict[source_subset_name].config_object.make_copy_of_config(des_path) 
        
        return True
    
    #==========================================================================
    def deprecated_rename_paths(self, from_name, to_name, pre_directory=''): 
        
        for name in self.paths.keys(): 
            if type(self.paths[name]) == dict:
                for sub_name in self.paths[name].keys():
                    self.paths[name][sub_name] = get_new_path(from_name, to_name, self.paths[name][sub_name], pre_directory)
            else:
                self.paths[name] = get_new_path(from_name, to_name, self.paths[name], pre_directory)
            
                
    #==========================================================================
    def deprecated_rename_subset(self, from_name=None, to_name=None): 
        """
        Renames the subset and changes all the paths. 
        """ 
        assert all([from_name, to_name]) 
        
        if to_name.lower() in ['subset', 'default_subset']: 
            self._logger.debug('Invalid name "{}" for subset!'.format(to_name)) 
            return False 
        
        if to_name in self.subset_dict.keys():
            self._logger.debug('Invalid name "{}" for subset! subset already excists!'.format(to_name)) 
            return False 
            
        subset_object = self.get_subset_object(from_name)
        
        subset_object.rename_subset(to_name)
        
        # Rename paths in Workspace 
        self.rename_paths(from_name, to_name, pre_directory='subsets')
        
        # Rename paths in step_0 
        self.step_0.rename_paths(from_name, to_name, pre_directory='subsets')
        
        # Rename key in dict 
        self.subset_dict[to_name] = self.subset_dict[from_name]
        self.subset_dict.pop(from_name)
        
    
    #==========================================================================
    def deprecated_rename_workspace(self, to_name=None): 
        """
        Renames the workspace and changes all the paths. 
        """  
        
        if not self._change_ok(): 
            self._logger.debug('Not allowed to rename workspace!') 
            return False  
            
        current_directory = self.paths['workspace_directory']
        new_directory = '{}/{}'.format(self.paths['parent_directory'], to_name) 
        
        if os.path.exists(new_directory):
            self._logger.debug('Workspace "{}" already excists. Can not rename workspace!'.format(to_name))
            return False
        
        # Rename paths in Workspace 
        self.rename_paths(self.name, to_name, pre_directory='workspaces')
        
        # Rename paths in step_0 
        self.step_0.rename_paths(self.name, to_name, pre_directory='workspaces') 
        
        # Rename subsets 
        for subset in self.subset_dict.keys():
            self.subset_dict[subset].rename_workspace(self.name, to_name)
        
        # Set path in config file 
        self.config_object.set_path(self.name, to_name, pre_directory='workspaces') 
        
        # Rename directory 
#        self._logger.debug(from_path)
#        self._logger.debug(to_path)
        os.rename(current_directory, new_directory)
        
        self.name = to_name 
        
    #==========================================================================
    def deprecated_make_copy_of_workspace(self, 
                               alias=None, 
                               unique_id=None, 
                               overwrite=False): 
        """
        Makes a copy of the workspace and loads all data and settings files. 
        
        Input: 
            workspace_name - name of the new workspace 
            overwrite - Tue/False
        Return: 
            workspace object for the new workspace
            Returns False if something went wrong 
        """ 
        
        # Initiating workspace
        new_workspace_path = '/'.join([self.paths['parent_directory'], unique_id])
        if os.path.exists(new_workspace_path): 
            self._logger.debug('New workspace already excists!')
            return False
        new_workspace_object = core.WorkSpace(alias=alias, 
                                              unique_id=unique_id,  
                                              parent_directory=self.paths['parent_directory'],
                                              resource_directory=self.paths['resource_directory']) 
        
        # Load config files. One for workspace and one for each subset. 
        # The config file are copies of the existing ones but with new uuid 
        # Workspace config 
        des_path = new_workspace_object.config_object.file_path 
        new_workspace_object.config_object = self.config_object.make_copy_of_config(des_path)
        
        # Set logger
        new_workspace_object.unique_id = new_workspace_object.config_object.get_unique_id()
        new_workspace_object.set_logger(new_workspace_object.unique_id)
        
        # Copy files to new workspace
        new_workspace_object._add_files_from_workspace(self, overwrite=overwrite) 

        # Subset configs
        for subset in new_workspace_object.subset_dict.keys(): 
            des_path = new_workspace_object.subset_dict[subset].config_object.file_path
            new_workspace_object.subset_dict[subset].config_object = self.subset_dict[subset].config_object.make_copy_of_config(des_path)
        
        # Load data in workspace 
        data_loaded = new_workspace_object.load_all_data()
        
        if data_loaded:
            self._logger.debug('Data loaded!')
        else:
            self._logger.debug('No data to load! Consider loading default data by calling <workspace_objetc>.load_default_data()')
            
        
        
        return new_workspace_object
        
        
    #==========================================================================
    def deprecated_add_files_from_workspace(self, workspace_object=None, overwrite=False):
        """
        Copy files from given workspace. Option to overwrite or not. 
        This method is used when copy an entire workspace. 
        """ 
        # Step 0
        if workspace_object.step_0: 
            self.step_0 = WorkStep(name='step_0', 
                          parent_directory=self.paths['workspace_directory'], 
                          mapping_objects=self.mapping_objects, 
                          parent_workspace_object=self) 
            self.step_0.add_files_from_workstep(step_object=workspace_object.step_0, 
                                                overwrite=overwrite)
                
        # Subsets
        for subset in workspace_object.get_subset_list():
            self._add_subset(subset)
            self.subset_dict[subset]._add_files_from_subset(subset_object=workspace_object.subset_dict[subset], 
                                                           overwrite=overwrite)
            
        # Data         
        for from_file_path in workspace_object.get_all_file_paths_in_input_data():
            to_file_path = from_file_path.replace(workspace_object.paths['workspace_directory'], self.paths['workspace_directory'])
            if os.path.exists(to_file_path) and not overwrite:
                continue
            to_directory = os.path.dirname(to_file_path)
            if not os.path.exists(to_directory):
                # If directory has been added in later versions of the ekostat calculator
                os.makedirs(to_directory)
            # Copy file
            shutil.copy(from_file_path, to_file_path)
        
 
    #==========================================================================
    def deprecated_apply_data_filter_step_0(self): 
        """
        Applies the first filter to the index_handler. 
        """
        all_ok = self.index_handler.add_filter(filter_object=self.step_0.data_filter, step='step_0')
        return all_ok
        
    #==========================================================================
    def deprecated_apply_subset_data_filter(self, subset):
        """
        Applies the data filter for the given subset. 
        This is not fully handled by the index_handler. 
        Filter is applyed in step 1.
        """
        if subset not in self.get_subset_list():
            return False
        sub_object = self.get_step_1_object(subset)
        all_ok = self.index_handler.add_filter(filter_object=sub_object.data_filter, filter_step=1, subset=subset)
        return all_ok
    
#==========================================================================
class IndicatorFileError(Exception):
    
    def __init__(self, expression, message):
        self.expression = expression
        self.message = message
#==========================================================================
class Config(dict): 
    def __init__(self, file_path): 
#        self.file_path = pathlib.Path(file_path)
        self.file_path = file_path
        
        # Log directories.
        if not os.path.exists(self.file_path):
            with codecs.open(self.file_path, 'w', encoding='cp1252') as fid: 
                fid.write('')
        else:
            with codecs.open(self.file_path, encoding='cp1252') as fid:
                for line in fid: 
                    line = line.strip()
                    if not line:
                        continue
                    split_line = [item.strip() for item in line.split(';')]
                    item, value = split_line
                    self[item] = value
    
    #==========================================================================
    def get_config(self, item):
        return self.get(item)
    
    #==========================================================================
    def set_config(self, item, value):
        self[item] = value
        self.save_file()
    
    #==========================================================================
    def set_unique_id(self, unique_id=None): 
        if not self.get('unique_id'):
#            if unique_id:
#                self['unique_id'] = unique_id
#            else:
            self['unique_id'] = str(uuid.uuid4())
            self.save_file()
        return self['unique_id']
    
    #==========================================================================
    def set_name(self, name): 
        self['name'] = name 
        self.save_file()
        
    #==========================================================================
    def get_name(self): 
        return self.get('name', False)
    
    #==========================================================================
    def get_unique_id(self): 
        return self.get('unique_id', False)
    
    #==========================================================================
    def save_file(self):
        with codecs.open(self.file_path, 'w', encoding='cp1252') as fid:
            for item, value in sorted(self.items()):
                line = ';'.join([item, value])
                fid.write('{}\n'.format(line)) 
                
    #==========================================================================
    def make_copy_of_config(self, file_path): 
        """
        Returns a copy of the config file. The copy will have a new unique_id. 
        """
        shutil.copyfile(self.file_path, file_path) 
        c = Config(file_path) 
        # Force new uuid
        c.set_config('unique_id', str(uuid.uuid4()))
        c.save_file()
        return c
    
    #==========================================================================
    def set_path(self, from_name, to_name, pre_directory): 
        self.file_path = get_new_path(from_name, to_name, self.file_path, pre_directory)
      
        
        
"""
###############################################################################
###############################################################################
###############################################################################
###############################################################################
###############################################################################
###############################################################################
###############################################################################
###############################################################################
###############################################################################
###############################################################################
###############################################################################
###############################################################################
"""


#==============================================================================
#==============================================================================
def get_step_name(step): 
#    self._logger.debug('STEP', step)
    if step == None:
        return step
    step = str(step)
    if not step.startswith('step_'):
        step = 'step_' + step
    return step


#==============================================================================
#==============================================================================
def get_new_path(from_name, to_name, old_path, pre_directory=''): 
    # include /p/ here to be safer when using replace for string. 
    from_string = '/{}/{}'.format(pre_directory, from_name)
    to_string = '/{}/{}'.format(pre_directory, to_name) 
    if old_path.endswith(from_name):
        from_string = from_string + '$'
    else:
        from_string = from_string + '/'
        to_string = to_string + '/' 
    
    return re.sub(from_string, to_string, old_path, 1)


#==============================================================================
#==============================================================================
#==============================================================================
if __name__ == '__main__':
    if 0:
        directory = 'D:/Utveckling/g_ekostat_calculator/ekostat_calculator_lena/workspaces/default'
        new_directory = 'D:/Utveckling/g_ekostat_calculator/ekostat_calculator_lena/workspaces/active_workspace'
        file_list = []
        new_file_list = []
        for root, dirs, files in os.walk(directory): 
    #            self._logger.debug(root.replace('\\', '/'))
    #             level = root.replace(directory, '').count(os.sep)
    #             indent = ' ' * 4 * (level)
    #             self._logger.debug('{}{}/'.format(indent, os.path.basename(root)))
    #             subindent = ' ' * 4 * (level + 1)
                for f in files:
    #                 file_list.append('/'.join([os.path.basename(root), f]))
                    file_path = '/'.join([root, f]).replace('\\', '/')
                    file_list.append(file_path)
                    new_file_path = file_path.replace(directory, new_directory)
                    new_file_list.append(new_file_path)
                    
    if 1:
        workspace_path = 'D:/Utveckling/g_ekostat_calculator/ekostat_calculator_lena/workspaces'
        w = WorkSpace(name='default', parent_directory=workspace_path)

