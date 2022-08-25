"""
Just to simplify functionality, we will create config as a dictionary and keep it here

CONFIG is read from 'config.yaml' as a dict

"""

import os
import yaml

CONFIG_FILE_NAME = os.path.join(os.getcwd(), 'config.yaml')

try:
    with open(CONFIG_FILE_NAME, 'r') as cfg_file:
        CONFIG = yaml.safe_load(cfg_file)
except FileNotFoundError:
    print('ERROR READING CONFIG, HAVE YOU CREATED config.yaml FROM A TEMPLATE??')
    raise
