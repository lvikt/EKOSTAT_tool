# coding: utf-8

# In[1]:


import os
import sys

path = "../"
path = "D:/github/w_vattenstatus/ekostat_calculator"
sys.path.append(path)
# os.path.abspath("../")
print(os.path.abspath(path))

# In[2]:


import pandas as pd
import time
import core
import importlib

importlib.reload(core)
import logging

importlib.reload(core)
try:
    logging.shutdown()
    importlib.reload(logging)
except:
    pass
from event_handler import EventHandler

print(core.__file__)
pd.__version__
###############################################################################################################################
# ### Load directories
root_directory = 'C:/github/w_vattenstatus/ekostat_calculator'  # "../" #os.getcwd()
workspace_directory = root_directory + '/workspaces'
resource_directory = root_directory + '/resources'

user_id = 'test_user'  # kanske ska vara off_line user?
# ## Initiate EventHandler
print(root_directory)
paths = {'user_id': user_id,
         'workspace_directory': root_directory + '/workspaces',
         'resource_directory': root_directory + '/resources',
         'log_directory': 'C:/github' + '/log',
         'test_data_directory': 'C:/github' + '/test_data',
         'cache_directory': 'C:/github/w_vattenstatus/cache'}

t0 = time.time()
ekos = EventHandler(**paths)
# request = ekos.test_requests['request_workspace_list']
# response = ekos.request_workspace_list(request)
# ekos.write_test_response('request_workspace_list', response)
print('-' * 50)
print('Time for request: {}'.format(time.time() - t0))
###############################################################################################################################
# ### set alias etc.
workspace_alias = 'test1'  # 'kustzon_selection'
# ### Make a new workspace
#ekos.copy_workspace(source_uuid='default_workspace', target_alias=workspace_alias)
# ### See existing workspaces and choose workspace name to load
ekos.print_workspaces()
workspace_uuid = ekos.get_unique_id_for_alias(workspace_alias=workspace_alias)  # 'kuszonsmodellen' lena_indicator
print(workspace_uuid)

workspace_alias = ekos.get_alias_for_unique_id(workspace_uuid=workspace_uuid)
###############################################################################################################################
# ### Load existing workspace
ekos.load_workspace(unique_id=workspace_uuid)
###############################################################################################################################
# ### Load all data in workspace
# #### if there is old data that you want to remove
ekos.get_workspace(workspace_uuid=workspace_uuid).delete_alldata_export()
ekos.get_workspace(workspace_uuid=workspace_uuid).delete_all_export_data()
###############################################################################################################################
# #### to just load existing data in workspace
ekos.load_data(workspace_uuid=workspace_uuid)
###############################################################################################################################
# ### check workspace data length
w = ekos.get_workspace(workspace_uuid=workspace_uuid)
len(w.data_handler.get_all_column_data_df())
###############################################################################################################################
# ### see subsets in data
for subset_uuid in w.get_subset_list():
    print('uuid {} alias {}'.format(subset_uuid, w.uuid_mapping.get_alias(unique_id=subset_uuid)))
###############################################################################################################################
# # Step 0
print(w.data_handler.all_data.columns)
###############################################################################################################################
# ### Apply first data filter
w.apply_data_filter(step=0)  # This sets the first level of data filter in the IndexHandler
###############################################################################################################################
# # Step 1
# ### make new subset
w.copy_subset(source_uuid='default_subset', target_alias='test1')
###############################################################################################################################
# ### Choose subset name to load
subset_alias = 'test1'  # 'SE1_selection'#'satellite_results'#'waters_export'#'test_subset'
subset_uuid = ekos.get_unique_id_for_alias(workspace_alias=workspace_alias, subset_alias=subset_alias)
print('subset_alias', subset_alias, 'subset_uuid', subset_uuid)
###############################################################################################################################
# ### Set subset filters
# #### year filter
w.set_data_filter(subset=subset_uuid, step=1,
                  filter_type='include_list',
                  filter_name='MYEAR',
                  data=[])  # ['2011', '2012', '2013']) #2007,2008,2009,2010,2011,2012 , 2014, 2015, 2016
###############################################################################################################################
# #### waterbody filter
w.set_data_filter(subset=subset_uuid, step=1,
                  filter_type='include_list',
                  filter_name='viss_eu_cd', data=[])

f1 = w.get_data_filter_object(subset=subset_uuid, step=1)
print(f1.include_list_filter)
print('subset_alias:', subset_alias, '\nsubset uuid:', subset_uuid)
f1 = w.get_data_filter_object(subset=subset_uuid, step=1)
print(f1.include_list_filter)
########################################################################################################################
# ## Apply step 1 datafilter to subset
w.apply_data_filter(subset=subset_uuid, step=1)
filtered_data = w.get_filtered_data(step=1, subset=subset_uuid)
########################################################################################################################
# Step 2
# Load indicator settings filter
w.get_step_object(step=2, subset=subset_uuid).load_indicator_settings_filters()
########################################################################################################################
# set available indicators
w.get_available_indicators(subset=subset_uuid, step=2)

########################################################################################################################
# ### choose indicators
# list(zip(typeA_list, df_step1.WATER_TYPE_AREA.unique()))
# indicator_list = ['oxygen','din_winter','ntot_summer', 'ntot_winter', 'dip_winter', 'ptot_summer', 'ptot_winter','bqi', 'biov', 'chl', 'secchi']
# indicator_list = ['din_winter','ntot_summer', 'ntot_winter', 'dip_winter', 'ptot_summer', 'ptot_winter']
# indicator_list = ['chl']
# indicator_list = ['secchisat']
# indicator_list = ['bqi', 'secchi'] + ['biov', 'chl'] + ['din_winter']
# indicator_list = ['din_winter','ntot_summer']
# indicator_list = ['indicator_' + indicator for indicator in indicator_list]
indicator_list = w.available_indicators
########################################################################################################################
# w.get_data_for_waterstool(step = 3, subset = subset_uuid, indicator_list = indicator_list)
# ### Apply indicator data filter
print('apply indicator data filter to {}'.format(indicator_list))
for indicator in indicator_list:
    w.apply_indicator_data_filter(step=2,
                                  subset=subset_uuid,
                                  indicator=indicator)
########################################################################################################################
# # Step 3
# ### Set up indicator objects
print('indicator set up to {}'.format(indicator_list))
w.get_step_object(step=3, subset=subset_uuid).indicator_setup(indicator_list=indicator_list)
########################################################################################################################
### CALCULATE STATUS
print('CALCULATE STATUS to {}'.format(indicator_list))
w.get_step_object(step=3, subset=subset_uuid).calculate_status(indicator_list=indicator_list)
#######################################################################################################################
### CALCULATE QUALITY ELEMENTS
w.get_step_object(step=3, subset=subset_uuid).calculate_quality_element(quality_element='nutrients_sw')
w.get_step_object(step=3, subset=subset_uuid).calculate_quality_element(quality_element='phytoplankton')
# w.get_step_object(step = 3, subset = subset_uuid).calculate_quality_element(quality_element = 'bottomfauna')
w.get_step_object(step=3, subset=subset_uuid).calculate_quality_element(quality_element='oxygen')
w.get_step_object(step=3, subset=subset_uuid).calculate_quality_element(quality_element='secchi')
#

print(10 * '*' + 'FINISHED' + 10 * '*')

