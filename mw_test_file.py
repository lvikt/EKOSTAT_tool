# -*- coding: utf-8 -*-

"""
Created on Mon Jul 10 15:27:01 2017

@author: a001985
"""
import os
import sys
import datetime
import est_core

    
    
    
###############################################################################
if __name__ == '__main__':
    nr_marks = 60
    print('='*nr_marks)
    print('Running module "mw_test_file.py"')
    print('-'*nr_marks)
    print('')
    
    root_directory = os.path.dirname(os.path.abspath(__file__))
    
#    est_core.StationList(root_directory + '/test_data/Stations_inside_med_typ_attribute_table_med_delar_av_utsjö.txt')
    est_core.ParameterList()
    
    #--------------------------------------------------------------------------
    # Directories and file paths
    raw_data_file_path = root_directory + '/test_data/raw_data/data_BAS_2000-2009.txt'
    first_filter_data_directory = root_directory + '/test_data/filtered_data' 
    
    first_data_filter_file_path = root_directory + '/test_data/filters/first_data_filter.txt' 
    winter_data_filter_file_path = root_directory + '/test_data/filters/winter_data_filter.txt'
    
    tolerance_filter_file_path = root_directory + '/test_data/filters/tolerance_filter_template.txt'
    
    #--------------------------------------------------------------------------
    # Filters 
    first_filter = est_core.DataFilter('First filter', file_path=first_data_filter_file_path)
    winter_filter = est_core.DataFilter('winter_filter', file_path=winter_data_filter_file_path)
    winter_filter.save_filter_file(root_directory + '/test_data/filters/winter_data_filter_save.txt') # mothod available
    tolerance_filter = est_core.ToleranceFilter('test_tolerance_filter', file_path=tolerance_filter_file_path)

    #--------------------------------------------------------------------------
    # Reference values
    est_core.RefValues()
    est_core.RefValues().add_ref_parameter_from_file('DIN_winter', root_directory + '/test_data/din_vinter.txt')
    est_core.RefValues().add_ref_parameter_from_file('TOTN_winter', root_directory + '/test_data/totn_vinter.txt')
    
    #--------------------------------------------------------------------------
    #--------------------------------------------------------------------------
    # Handler (raw data)
    raw_data = est_core.DataHandler('raw')
    raw_data.add_txt_file(raw_data_file_path, data_type='column') 
    
    # Use first filter 
    filtered_data = raw_data.filter_data(first_filter) 
    
    # Save filtered data (first filter) as a test
    filtered_data.save_data(first_filter_data_directory)
    
    
    # Load filtered data (first filter) as a test
    loaded_filtered_data = est_core.DataHandler('first_filtered')
    loaded_filtered_data.load_data(first_filter_data_directory)


    # Create and fill QualityFactor
    qf_NP = est_core.QualityFactorNP()
    qf_NP.set_data_handler(data_handler=loaded_filtered_data)
    
    # Filter parameters in QualityFactorNP 
    # First general filter 
    qf_NP.filter_data(data_filter_object=first_filter) 
    # winter filter
    qf_NP.filter_data(data_filter_object=winter_filter, indicator='TOTN_winter') 
    
    q_factor = qf_NP.get_quality_factor(tolerance_filter)
    
    
    # Parameter
    print('-'*nr_marks)
    print('done')
    print('-'*nr_marks)
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    