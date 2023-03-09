import numpy as np

def Chi2_polyval(x: np.array, y: np.array, param: np.array):
    """
    Returns Chi square functional for np.polyfit approximation
    """
    approximation = np.polyval(param,x)
    squared_error = np.square((np.asarray(y) - approximation))/approximation

    return np.sum(squared_error)/(len(x)-len(param))

def get_first_intersection(x: np.array, y: np.array, value: np.array):
    '''
    Finds the first intersection of y = value and curve y = f(x)
    '''
    return x[np.argmax(y > value)]

def is_iterable(x):
    '''
    Checks if the given element x is iterable
    '''
    try:
        iterator = iter(x)
        return True
    except TypeError:
        return False