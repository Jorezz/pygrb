import requests
from bs4 import BeautifulSoup
from astropy.time import Time
from functools import lru_cache

@lru_cache(maxsize = 100)
def parse_datetime_from_response_text(text, time_tag):
    '''
    Parse datetime from response text from heasarc
    Args:
        text: response text
        time_tag: time tag in response text, 'ijd' = 'time_out_ii', 'utc' = 'time_out_i'
    Returns:
        str: datetime in requested format
    '''
    ob = BeautifulSoup(text,'lxml')
    category = ob.find_all("td", {"id" : time_tag})
    return ' '.join(category[0].string.split())

def get_utc_from_ijd(ijd_time: float) -> str:
    return Time(51544 + ijd_time, format='mjd', scale = 'tt').utc.to_value('iso', subfmt='date_hms')

def get_ijd_from_utc(utc_time: str) -> float:
    '''
    Converts Integral Julian Date to UTC using astropy
    Args:
        utc_time (str): datetime to convert
    '''
    time = utc_time[:10]+'T'+utc_time[11:]
    return Time(time, format='isot', scale='utc').tt.mjd - 54144

def get_utc_from_Fermi_seconds(fermi_seconds):
    url = f'https://heasarc.gsfc.nasa.gov/cgi-bin/Tools/xTime/xTime.pl?time_in_i=&time_in_c=&time_in_d=&time_in_j=&time_in_m=&time_in_sf={fermi_seconds}&time_in_wf=&time_in_ii=&time_in_sl=&time_in_sni=&time_in_snu=&time_in_s=&time_in_h=&time_in_sz=&time_in_ss=&time_in_sn=&timesys_in=u&timesys_out=u&apply_clock_offset=yes'
    response = requests.get(url)
    return parse_datetime_from_response_text(response.text, "time_out_i")

def get_ijd_from_Fermi_seconds(fermi_seconds) -> float:
    url = f'https://heasarc.gsfc.nasa.gov/cgi-bin/Tools/xTime/xTime.pl?time_in_i=&time_in_c=&time_in_d=&time_in_j=&time_in_m=&time_in_sf={fermi_seconds}&time_in_wf=&time_in_ii=&time_in_sl=&time_in_sni=&time_in_snu=&time_in_s=&time_in_h=&time_in_sz=&time_in_ss=&time_in_sn=&timesys_in=u&timesys_out=u&apply_clock_offset=yes'
    response = requests.get(url)
    return float(parse_datetime_from_response_text(response.text, "time_out_ii"))