import requests
import pandas as pd
import datetime
import numpy as np
from .config import ACS_DATA_PATH, LIGHT_CURVE_SAVE, GBM_DETECTOR_CODES, logging
from astropy.io import fits
import matplotlib.pyplot as plt
from .time import get_ijd_from_utc, get_ijd_from_Fermi_seconds
import pickle


class LightCurve():
    '''
    Base class for light curves from different sources
    '''
    def __init__(self, event_time: str = None,duration: float = None, data: np.array = None):
        '''
        Args:
            event_time (str, optional): time of the event in format 'YYYY-MM-DD HH:MM:SS'
            duration (int, optional): duration in seconds
            data (np.array, optional): data of the light curve
        '''
        self.event_time = event_time
        self.duration = duration

        if data is not None:
            self.__get_light_curve_from_data(data)
        else:
            self.times = None
            self.times_err = None
            self.signal = None
            self.signal_err = None
            self.resolution = None

            self.original_times,self.original_signal = None, None
            self.original_resolution = None

    def __repr__(self):
        return f'{self.__class__.__name__}(event_time={self.event_time}, duration={self.duration}, original resolution={self.original_resolution})'

    def __eq__(self, other: object):
        return isinstance(other, LightCurve) and self.__class__ == other.__class__ and self.event_time == other.event_time and self.duration == other.duration and self.original_resolution == other.original_resolution

    def plot(self,kind: str = 'plot',logx: bool = None,logy: bool = None, **kwargs):
        '''
        Plot the light curve
        Args:
            kind (str, optional): plotting method
            logx (bool, optional): log x axis
            logy (bool, optional): log y axis
            kwargs (dict, optional): keyword arguments for plotting used by matplotlib.pyplot.plot
        '''
        if kind == 'plot':
            plt.plot(self.times, self.signal, **kwargs)
        elif kind == 'errorbar':
            plt.errorbar(self.times, self.signal, xerr=self.times_err, yerr=self.signal_err, fmt = 'o', **kwargs)
        elif kind == 'scatter':
            plt.scatter(self.times, self.signal, **kwargs)
        elif kind == 'step':
            plt.step(self.times, self.signal, **kwargs)
        else:
            raise NotImplementedError(f'Plotting method {kind} not supported')

        if logx:
            plt.xscale('log')
        if logy:
            plt.yscale('log')

    @staticmethod
    def _rebin_data(times,signal,resolution,bin_duration: float = None, binning: np.array = None):

        '''
        Auxiliary method for rebining the light curve

        '''
        if binning is None:
            binning = np.linspace(times[0]-resolution+bin_duration,
                                  times[-1]+resolution-bin_duration,
                                  num=int(((times[-1]-resolution) - (times[0]+resolution))/bin_duration))

        bined_signal = np.asarray([np.sum(signal[(times>time-bin_duration/2)&(times<=time+bin_duration/2)]) for time in binning])
        bined_signal_err = np.asarray([np.std(signal[(times>time-bin_duration/2)&(times<=time+bin_duration/2)]) for time in binning])
        bined_times = np.asarray([time for time in binning])
        bined_times_err = np.asarray([bin_duration/2 for time in binning])

        return bined_times,bined_times_err,bined_signal,bined_signal_err,binning

    def rebin(self,bin_duration: float = None, reset: bool = True):
        '''
        Rebin light curve from original time resolution
        Args:
            bin_duration (float): new bin duration in seconds, if None, return to original resolution
            reset (bool, optional): if True, rebin the light curve using original resolution, result is same as self.rebin().rebin(bin_duration)
        Returns:
            self
        '''
        if bin_duration is None:
            self.times = self.original_times
            self.times_err = np.full(self.original_times.shape[0], self.original_resolution)
            self.signal = self.original_signal
            self.signal_err = np.sqrt(self.original_signal)
            self.resolution = self.original_resolution

            return self

        if reset:
            bined_times, bined_times_err, bined_signal, bined_signal_err, _ = self._rebin_data(self.original_times, self.original_signal, self.original_resolution, bin_duration)
        else:
            bined_times, bined_times_err, bined_signal, bined_signal_err, _ = self._rebin_data(self.times, self.signal, self.resolution, bin_duration)
        
        self.signal = bined_signal
        self.signal_err = bined_signal_err
        self.times = bined_times
        self.times_err = bined_times_err
        self.resolution = bin_duration

        return self

    def set_intervals(self,*intervals):
        """
        Returns light curve in intervals
        Args:
            *intervals: tuples (start_time,end_time),(start_time,end_time),...
        Returns:
            self
        """
        if len(intervals)==0:
            return self.times,self.times_err,self.signal,self.signal_err
        else:
            temp_time=[]
            temp_time_err=[]
            temp_signal=[]
            temp_signal_err=[]
            for interval in intervals:
                for i,time in enumerate(self.times):
                    if interval[0] < time < interval[1]:
                        temp_time.append(time)
                        temp_time_err.append(self.times_err[i])
                        temp_signal.append(self.signal[i])
                        temp_signal_err.append(self.signal_err[i])

            self.times= np.asarray(temp_time)
            self.times_err = np.asarray(temp_time_err)
            self.signal = np.asarray(temp_signal)
            self.signal_err = np.asarray(temp_signal_err)

            return self
        
    def substract_polynom(self,polynom_params: np.array):
        '''
        Substract polynom from light curve
        Args:
            polynom_params (np.array): parameters for polynom to be subtracted, from np.polyfit
        Returns:
            self
        '''
        self.signal = self.signal - np.polyval(polynom_params,self.times)
        return self

    def filter_peaks(self,peak_threshold: float = -3):
        '''
        Filter light curve to remove peaks
        Args:
            peak_threshold (float, optional): threshold for peak removal, if negative - remove points bellow median, if positive - remove points above median
        Returns:
            self
        '''
        median_flux = np.median(self.signal)

        if peak_threshold < 0:
            indexes_to_remove = (self.signal - median_flux)/np.where(np.nan_to_num(self.signal_err,nan=1)==0,1,np.nan_to_num(self.signal_err,nan=1)) < peak_threshold
        else:
            indexes_to_remove = (self.signal - median_flux)/np.where(np.nan_to_num(self.signal_err,nan=1)==0,1,np.nan_to_num(self.signal_err,nan=1)) >= peak_threshold

        self.signal = np.delete(self.signal, indexes_to_remove)
        self.signal_err = np.delete(self.signal_err, indexes_to_remove)
        self.times = np.delete(self.times, indexes_to_remove)
        self.times_err = np.delete(self.times_err, indexes_to_remove)
        
        return self

    def __get_light_curve_from_data(self,data):
        '''
        Appends data from data to light curve object
        Args:
            data (np.array): data array with shape (n_samples,n_channels), where n_channels is 2 or 4
        '''
        if data.shape[1] == 2:
            self.original_times = data[:,0]
            self.original_signal = data[:,1]
            
            self.times = self.original_times
            self.original_resolution = round(np.mean(self.times[1:] - self.times[:-1]),3) # determine size of time window
            self.times_err = np.full(self.original_times.shape[0], self.original_resolution)
            self.signal = self.original_signal
            self.signal_err = np.sqrt(self.original_signal)
            self.resolution = self.original_resolution
        elif data.shape[1] == 4:
            self.original_times = data[:,0]
            self.original_signal = data[:,2]
            
            self.times = self.original_times
            self.original_resolution = round(np.mean(self.times[1:] - self.times[:-1]),3) # determine size of time window
            self.times_err = data[:,1]
            self.signal = self.original_signal
            self.signal_err = data[:,3]
            self.resolution = self.original_resolution

    @classmethod
    def load(cls,filename: str):

        '''
        Load light curve from file without extension
        '''
        with open(f'{LIGHT_CURVE_SAVE}{filename}.pkl','rb') as f:
            cls = pickle.load(f)
        return cls

    def save(self,filename: str = None):
        '''
        Save light curve to file
        Args:
            filename (str, optional): file name without extension
        '''
        filename = filename if filename else f'{self.event_time[0:10]}_{self.event_time[11:13]}_{self.event_time[14:16]}_{self.event_time[17:19]}__{self.duration}__{self.original_resolution}'
        with open(f'{LIGHT_CURVE_SAVE}{filename}.pkl','wb') as f:
            pickle.dump(self,f)



class SPI_ACS_LightCurve(LightCurve):
    '''
    Class for light curves from SPI-ACS/INTEGRAL
    '''
    def __init__(self,event_time: str,duration: int, loading_method: str='local',scale: str='utc',**kwargs):
        '''
        Args:
            event_time (str): date and time of event
            duration (int): duration of light curve in seconds
            loading_method (str, optional): 'local' or 'web'
            scale (str, optional): 'utc' or 'ijd'
        '''
        super().__init__(event_time,duration,**kwargs)

        if self.original_times is None:
            if loading_method == 'local':
                self.original_times,self.original_signal = self.__get_light_curve_from_file(scale = scale)
            elif loading_method =='web':
                self.original_times,self.original_signal = self.__get_light_curve_from_web(scale = scale)
            else:
                raise NotImplementedError(f'Loading method {loading_method} not supported')

            self.times = self.original_times
            self.original_resolution = round(np.mean(self.times[1:] - self.times[:-1]),3) # determine size of time window
            self.times_err = np.full(self.original_times.shape[0], self.original_resolution)
            self.signal = self.original_signal
            self.signal_err = np.sqrt(self.original_signal)
            self.resolution = self.original_resolution
        

    def __get_light_curve_from_file(self,scale = 'utc'):
        '''
        Load a light curve from raw scw files
        Args:
            scale (str, optional): scale of light curve, 'utc' (seconds from trigger) or 'ijd' (days from J2000)
        '''
        acs_scw_df= []
        with open(f'{ACS_DATA_PATH}swg_infoc.dat','r') as f:
            for line in f:
                acs_scw_df.append(line.split())

        acs_scw_df = pd.DataFrame(acs_scw_df,columns=['scw_id','obt_start','obt_finish','ijd_start','ijd_finish','scw_duration','x','y','z','ra','dec'])
        acs_scw_df['scw_id'] = acs_scw_df['scw_id'].astype(str)
        acs_scw_df['ijd_start'] = acs_scw_df['ijd_start'].astype(float)
        acs_scw_df['ijd_finish'] = acs_scw_df['ijd_finish'].astype(float)

        center_time = datetime.datetime.strptime(self.event_time,'%Y-%m-%d %H:%M:%S')
        left_time = float(get_ijd_from_utc((center_time - datetime.timedelta(seconds=self.duration)).strftime('%Y-%m-%d %H:%M:%S')))
        right_time = float(get_ijd_from_utc((center_time + datetime.timedelta(seconds=self.duration)).strftime('%Y-%m-%d %H:%M:%S')))
        scw_needed = acs_scw_df[((acs_scw_df['ijd_start']>left_time)&(acs_scw_df['ijd_start']<right_time))|((acs_scw_df['ijd_finish']>left_time)&(acs_scw_df['ijd_finish']<right_time))|((acs_scw_df['ijd_start']<left_time)&(acs_scw_df['ijd_finish']>left_time))|((acs_scw_df['ijd_start']<right_time)&(acs_scw_df['ijd_finish']>right_time))]
        if scw_needed.shape[0]==0:
            raise ValueError(f'No data found for {self.event_time}')

        current_data = []
        for _,row in scw_needed.iterrows():
            for i in range(5):
                try:
                    with open(f'{ACS_DATA_PATH}0.05s/{row["scw_id"][:4]}/{row["scw_id"]}.00{i}.dat','r') as f:
                        for line in f:
                            line = line.split()
                            if float(line[0]) > 0:
                                current_data.append([row['ijd_start']+float(line[0])/(24*60*60),float(line[2])])
                    break
                except FileNotFoundError:
                    continue
            
        current_data = np.asarray(current_data)
        
        current_data[:,0] = (current_data[:,0] - (left_time+self.duration/(24*60*60)))*(24*60*60)
        current_data = current_data[np.abs(current_data[:,0])<self.duration]

        if scale == 'ijd':
            current_data[:,0] = current_data[:,0]/(24*60*60) + (left_time+self.duration/(24*60*60))

        return current_data[:,0],current_data[:,1]

    def __get_light_curve_from_web(self,scale = 'utc'):
        '''
        Download light curve from isdc (unavailable in Russia)
        Args:
            scale (str, optional): scale of light curve, 'utc' (seconds from trigger) or 'ijd' (days from J2000)
        '''
        url = f'https://www.isdc.unige.ch/~savchenk/spiacs-online/spiacs.pl?requeststring={self.event_time[0:10]}T{self.event_time[11:13]}%3A{self.event_time[14:16]}%3A{self.event_time[17:19]}+{self.duration}&generate=ipnlc&submit=Submit'
        data = np.asarray([[float(x.split()[0]),int(float(x.split()[1]))] for x in requests.get(url).text.split('<br>\n')[2:-2]])

        times=data[:,0]
        signal=data[:,1]
        gap=0.05
        temp_times=[]
        temp_signal=[]
        temp_times.append(times[0])
        temp_signal.append(signal[0] if np.isfinite(signal[0]) else 0)
        
        # Fill missing values
        counter=1
        while counter<len(times):
            if times[counter]>1.5*gap+temp_times[counter-1]:
                temp_times.append(temp_times[counter-1]+gap)
                temp_signal.append(0)
            else:
                temp_times.append(times[counter])
                temp_signal.append(signal[counter] if np.isfinite(signal[counter]) else 0)
                counter += 1

        temp_times = np.asarray(temp_times)
        temp_signal = np.asarray(temp_signal)
        if scale == 'ijd':
            event_time_ijd = get_ijd_from_utc(self.event_time)
            temp_times = temp_times/(24*60*60) + event_time_ijd

        return temp_times,temp_signal



class GBM_LightCurve(LightCurve):
    '''
    Class for light curves from GBM/Fermi
    '''
    def __init__(self,code: str, 
                 detector_mask: str,
                 redshift: float = None, 
                 original_resolution: float = None,
                 loading_method: str='web', 
                 scale = 'utc',
                 apply_redshift: bool = True,
                 filter_energy: dict = None,
                 save_photons: bool = False,
                 **kwargs):
        '''
        Args:
            code (str): GBM code, starting with 'bn', for example 'bn220101215'
            detector_mask (str): GBM detector mask
            redshift (float, optional): Cosmological redshift of GRB, if known
            original_resolution (float, optional): Starting binning of GRB, default to 0.01 seconds
            loading_method (str, optional): Method of obtaining the light curve, can be 'web' or 'local'
            scale (str, optional): Scale of the light curve, can be 'utc' or 'ijd', default to 'utc'
            apply_redshift (bool, optional): Apply redshift to the light curve, default to True
            filter_energy (dict, optional): Apply energy filter to the light curve, dict with low and high energy shoud be provided, otherwise None
            save_photons (bool, optional): Save the photons data from detectors, carefull, it can take a lot of memory, default to False
        '''
        super().__init__(code,**kwargs)
        self.code = code
        self.redshift = redshift if redshift else 0
        self.photon_data = {}
        self.original_resolution = original_resolution if original_resolution else 0.01
        self.resolution = self.original_resolution

        if self.original_times is None:
            if loading_method == 'web':
                self.original_times,self.original_signal = self.__get_light_curve_from_web(detector_mask, apply_redshift, filter_energy, save_photons, scale = scale)
            else:
                NotImplementedError(f'Loading method {loading_method} not implemented')

            self.times = self.original_times
            self.times_err = np.full(self.original_times.shape[0], self.original_resolution)
            self.signal = self.original_signal
            self.signal_err = np.sqrt(self.original_signal)
            
    def __get_light_curve_from_web(self,detector_mask: str, apply_redshift: bool, filter_energy: bool, save_photons: bool,scale = 'utc'):
        '''
        Binds the light curve from individual photons in lumined detectors
        Args:
            detector_mask (str): GBM detector mask, which detectors are the most luminous
            apply_redshift (bool, optional): Whether to apply the redshift to the light curve
            filter_energy (bool, optional): Whether to filter the light curve by energy
            scale (str, optional): scale of light curve, 'utc' (seconds from trigger) or 'ijd' (days from J2000)
        '''
        binning = None
        times_array = []
        signal_array = []
        lumin_detectors = [GBM_DETECTOR_CODES[i] for i,value in enumerate(list(detector_mask)) if value == '1']
        logging.info(f'Found {len(lumin_detectors)} luminous detectors')
        for detector in lumin_detectors:
            logging.info(f'Getting data for detector {detector}')
            hdul = self.load_fits(detector)
            ebounds = {line[0]:np.sqrt(line[1]*line[2]) for line in hdul[1].data}
            tzero = float(hdul[2].header['TZERO1'])
            data_df = pd.DataFrame(hdul[2].data)
            data_df['TIME'] = data_df['TIME'] - tzero
            data_df['PHA'] = data_df['PHA'].apply(lambda x:ebounds[x])
            data = data_df.values
            del data_df
            if apply_redshift:
                data[:,0], data[:,1] = self.apply_redshift(data[:,0], data[:,1],self.redshift)
            if filter_energy is not None:
                data = self.filter_energy(data,**filter_energy)

            if scale == 'ijd':
                trigger_time_ijd = get_ijd_from_Fermi_seconds(tzero)
                data[:,0] = data[:,0]/(24*60*60) + trigger_time_ijd

            self.photon_data = None
            if save_photons:
                if self.photon_data is None:
                    self.photon_data = data
                else:
                    self.photon_data = np.concatenate((self.photon_data,data))

            bined_times,_,bined_signal,_,binning = self._rebin_data(data[:,0],np.full(data.shape[0],1),0,self.original_resolution,binning)
            times_array.append(bined_times)
            signal_array.append(bined_signal)
            
        times = np.mean(times_array,axis=0)[1:-2]
        signal = np.sum(signal_array,axis=0)[1:-2]
            
        return times,signal
    
    def load_fits(self, detector: str):
        '''
        Loads fits file from heasarc server
        Args:
            detector (str): GBM detector code
        Returns:
            astropy.io.fits
        '''
        for i in range(5):
            try:
                return fits.open(f'https://heasarc.gsfc.nasa.gov/FTP/fermi/data/gbm/bursts/20{self.code[2]}{self.code[3]}/{self.code}/current/glg_tte_{detector}_{self.code}_v0{i}.fit')
            except requests.exceptions.HTTPError:
                pass
        raise ValueError(f'No data found for {self.code} detector {detector}') 
        
    @staticmethod
    def filter_energy(data: np.ndarray, low_en: float = 6, high_en: float = 850, detector: str = 'n0'):
        '''
        Filter the energy of the light curve
        Args:
            data (np.ndarray): time of photons and threir energy
            low_en (float, optional): Low energy threshold
            high_en (float, optional): High energy threshold
            detector (str, optional): GBM detector code
        '''
        if detector[0] == 'b':
            low_en = low_en if low_en else 200
            high_en = high_en if high_en else 6500
        elif detector[0] == 'n':
            low_en = low_en if low_en else  6
            high_en = high_en if high_en else 850
            
        return data[(data[:,1]>low_en)&(data[:,1]<high_en)]
            
    @staticmethod
    def apply_redshift(times: np.array, signal: np.array, redshift: float):
        '''
        Apply redshift to data
        Args:
            times (np.array): time of photons and their energy
            redshift (float): Cosmological redshift
        '''
        signal = signal * (1 + redshift)
        times = times / (1 + redshift)
        return times, signal



class IREM_LightCurve(LightCurve):
    '''
    Class for light curves from IREM/INTEGRAL
    '''
    def __init__(self,center_time,duration, loading_method: str='local', scale: str='utc', *args, **kwargs):
        #todo
        pass



def exclude_time_interval(times: np.array, signal: np.array, intervals):
    if type(intervals[0]) == tuple:
        mask = None
        for interval in intervals:
            if mask is None:
                mask = (times < interval[0]) | (times > interval[1])
            else:
                mask = mask & ((times < interval[0]) | (times > interval[1]))
    else:
        mask = (times < intervals[0]) | (times > intervals[1])

    return times[mask], signal[mask]

def limit_to_time_interval(times: np.array, signal: np.array, intervals):
    if type(intervals[0]) == tuple:
        mask = None
        for interval in intervals:
            if mask is None:
                mask = (times >= interval[0]) & (times <= interval[1])
            else:
                mask = mask | ((times >= interval[0]) & (times <= interval[1]))
    else:
        mask = (times >= intervals[0]) & (times <= intervals[1])

    return times[mask], signal[mask]