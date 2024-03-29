from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup
from datetime import datetime
from configparser import ConfigParser, NoOptionError, NoSectionError
from functools import lru_cache

import requests
import traceback

#{{{ init fast api
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
#}}}

#{{{ configparser
@lru_cache
def get_config(_section_config='', _default=''):
    """
    Retrieves configuration and parse it
    """
    config = ConfigParser()

    config.read('config.ini')

    def config_get(section_option, default=''):
        section, option = section_option.split('.')
        try:
            return config.get(section, option)
        except (NoOptionError, NoSectionError):
            return default

    config['user']['name'] = config_get('user.name')
    config['user']['password'] = config_get('user.password')

    if _section_config:
        return config_get(_section_config, _default)

    return config

#}}}

#{{{ prepare session
username = get_config('user.name')
password = get_config('user.password')

URLS = {
        'login': 'https://app.eps-int.com/login',
        'home': 'https://app.eps-int.com/TrackingPaquetes#filter=*',
        }

# start the session
session = requests.Session()

# create the payload
payload = {
        'username': username,
        'password': password,
        }

def is_logged_in():
    """
    Checks if the user is logged in on the page eps.com.do
    """
    cookies = session.cookies.get_dict()
    return 'WebSite_autologin' in cookies

# login into the session
def login():
    """Login to eps.com.do"""
    session.post(URLS['login'], data=payload)

#}}}

#{{{ constants
INITIAL_STATE = {
        'items': [],
        }

CACHE = {
        'home': '',
        'last_update': 0,
        }
#}}}

#{{{ routes
@app.get('/')
def packages():
    """
    Returns a list of packages from EPS.com

    This endpoint updates every hour
    """
    return get_packages()

@app.get('/now')
def now():
    """
    Returns a list of packages from EPS.com

    This will update every time you request this endpoint
    """
    return get_packages(use_cache=False)

@app.get('/clear')
def clear():
    """
    Clear cache session
    """
    CACHE['home'] = ''
    return 'OK'
#}}}

#{{{ get_packages
def get_packages(use_cache=True):
    """
    Fetch packages from EPS.com into a JSON format
    """

    clear = False
    epoch = datetime.now().timestamp()

    # elapsed minutes
    server_cache = float(get_config('server.cache', 30))
    epoch_difference = abs((CACHE['last_update'] - epoch))
    epoch_difference_to_minutes = epoch_difference / 60

    # if more an hour has passed clean the counter
    if epoch_difference_to_minutes > server_cache:
        CACHE['last_update'] = epoch
        clear = True

    # empty the cache every hour
    if clear and use_cache:
        CACHE['home'] = ''

    # fetch home
    if CACHE['home'] and use_cache:
        log('CACHE: CACHE')
        eps_home = CACHE['home']
    else:
        log('CACHE: DIRECT')
        login()
        eps_home = session.get(URLS['home'])
        CACHE['home'] = eps_home
        CACHE['last_update'] = epoch

    if not is_logged_in():
        return INITIAL_STATE

    # parse html
    soup = BeautifulSoup(eps_home.text, 'html.parser')

    soup_packages = soup.select('#fTrackingPaquetes [data-groups]')

    package_list = list(map(transform_package, soup_packages))

    return {
            'items': package_list,
            'logged_in': is_logged_in(),
            }
#}}}

#{{{ transform_package
def transform_package(soup):
    """
    Parse eps html item into a structure
    """
    status_mapper = {
            'status1': 'origin',
            'status2': 'air line / ship',
            'status3': 'customs',
            'status4': 'distribution center',
            'status6': 'transit',
            'status5': 'available',
            'status7': 'availableV2',
            }

    def get_first(arr):
        if bool(len(arr)):
            return arr[0]
        return ''

    try:
        # attributes
        groups = soup['data-groups']
        _, status, status_label = groups.split()
        condition = get_first(soup.find(class_='packagecondition').contents)
        tracking_number = get_first(soup.find(class_='trackingnumber').contents)
        content = get_first(soup.find(class_='packagecontent').contents)
        sender = get_first(soup.find(class_='packagesender').contents)
        weight = get_first(soup.find(class_='packageweight').contents)
    except Exception as e:
        # return empty item and print error just in case
        print(traceback.format_exc())
        return {}

    # return item
    return {
            'condition': condition,
            'trackingNumber': tracking_number,
            'content': content,
            'sender': sender,
            'weight': weight,
            'status': status,
            'statusLabel': status_label,
            'statusFormatted': status_mapper.get(status, 'na'),
            }
#}}}

#{{{ log
def log(message):
    """
    Log message with a predefined format
    """
    print(f'[Log]\t  {datetime.now()}\t{message}\n')
#}}}
