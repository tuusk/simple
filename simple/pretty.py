# -*- coding: utf-8 -*-
from tqdm.auto import tqdm
import pandas as pd
from pandas.io.formats.style import Styler
import numpy as np
from joblib import Parallel, delayed, cpu_count
import inspect
from psutil import cpu_percent
from datetime import datetime, timedelta
import matplotlib as mpl
from itertools import product


class tqdmParallel(Parallel):
    """Show progress bar when parallel processing"""

    def __init__(self, n_jobs=-1, progress=True, total=None, postfix=None, *args, **kwargs):
        self._progress = progress
        self._total = total
        self._lasttime = datetime.now()
        self._postfix = postfix if type(postfix) == dict else {'name': postfix} if postfix is not None else None
        super().__init__(n_jobs=n_jobs, *args, **kwargs)

    def __call__(self, *args, **kwargs):
        with tqdm(disable=not self._progress, total=self._total) as self._pbar:
            return Parallel.__call__(self, *args, **kwargs)

    def print_progress(self):
        if self._total is None:
            self._pbar.total = self.n_dispatched_tasks
        self._pbar.n = self.n_completed_tasks

        if datetime.now() > self._lasttime + timedelta(milliseconds=500):
            postfix = {'cpu': f'{cpu_percent():1.0f}%'}
            if self._postfix is not None:
                postfix = {**postfix, **self._postfix}  # merge dict operator with python 3.8 compatibility

            self._pbar.set_postfix(postfix, refresh=True)
            self._lasttime = datetime.now()


def tpl(x):
    """Convert value/dict to tuple"""
    return x if isinstance(x, tuple) else tuple(x.values()) if isinstance(x, dict) else (x,)


def plist(*args):
    """Creates product parameter list from a bunch of iterables/values"""
    return list(product(*(p if iterable(p) else [p] for p in args)))


def pmap(func: callable, *args, **kwargs):
    """Parallel map/starmap implementation via tqdmParallel"""

    param_list = plist(*args)
    with tqdmParallel(total=len(param_list), **kwargs) as P:
        FUNC = delayed(func)
        return P(FUNC(*tpl(param)) for param in param_list)


def iterable(obj):
    if type(obj) == str:
        return False

    try:
        iter(obj)
        return True
    except:
        return False


def pxmap(func: callable, param, **kwargs):
    """Another parallel map implementation, returns DataFrame, supports many parameters and results"""

    param_names = inspect.getfullargspec(func).args
    param_list = list(param)

    with tqdmParallel(total=len(param_list),  **kwargs) as P:
        FUNC = delayed(func)
        X = list(P(FUNC(*tpl(param)) for param in param_list))

    # append result names
    if len(X) > 0:
        if type(X[0]) == dict:
            param_names.extend(X[0].keys())
        elif type(X[0]) == tuple:
            param_names.extend([f'result_{n}' for n in range(len(X[0]))])
        else:
            param_names.append('result')

    return pd.DataFrame([(*tpl(x[0]), *tpl(x[1])) for x in zip(param_list, X)], columns=param_names)


def prun(indicator: callable, src, period: int, threads: int = cpu_count(), progress: bool = True) -> np.array:
    """Parallel calculate any indicator by slicing source series"""
    page_size = (len(src) - period + (threads - 1)) // threads
    start_indexes = [t * page_size for t in range(threads)]
    result_indexes = list(range(period, len(src), page_size))

    with tqdmParallel(total=len(start_indexes), n_jobs=threads, require='sharedmem', progress=progress) as P:
        FUNC = delayed(indicator)
        slice_size = period + page_size
        X = P(FUNC(src[start:start + slice_size], period) for start in start_indexes)

    # store all slices to the result series
    result = np.zeros(len(src))
    for page_start, x in zip(result_indexes, X):
        m = page_start + page_size
        page_stop = m if m < len(result) else len(result)
        result[page_start:page_stop] = x[period:]

    # fill prefix with first value
    result[:period] = result[period]
    return result


def Corr(X, Y):
    """Correlation coefficient"""
    return np.corrcoef(np.nan_to_num(X), np.nan_to_num(Y))[0, 1] * 100


def background(self, scale='Linear', cmap='RdYlGn', **css) -> pd.DataFrame:
    """For use with `DataFrame.style.apply` this function will apply a heatmap color gradient *elementwise* to the calling DataFrame

    self : pd.DataFrame
        The calling DataFrame. This argument is automatically passed in by the `DataFrame.style.apply` method

    cmap : colormap or str
        The colormap to use

    css : dict
        Any extra inline css key/value pars to pass to the styler

    Returns
    -------
    pd.DataFrame
        The css styles to apply to the calling DataFrame
    """
    cvals = self.fillna(0).values.ravel().copy()

    q = np.percentile(cvals, 99.9)
    vmax = max(cvals.max(), abs(np.clip(cvals, -q, q).min()))
    if scale == 'Linear':
        norm = mpl.colors.Normalize(vmin=-vmax, vmax=vmax, clip=True)  # Linear colorscale
    else:
        norm = mpl.colors.SymLogNorm(linthresh=1, vmin=-vmax, vmax=vmax, clip=True,
                                     base=2.17)  # Logarithmic color scale
    mapper = mpl.cm.ScalarMappable(norm=norm, cmap=cmap)

    styles = []
    for c in cvals:
        rgb = mapper.to_rgba(c)
        style = ["{}: {}".format(key.replace('_', '-'), value) for key, value in css.items()]
        style.append("background-color: {}".format(mpl.colors.rgb2hex(rgb)))
        styles.append('; '.join(style))
    styles = np.asarray(styles).reshape(self.shape)
    return pd.DataFrame(styles, index=self.index, columns=self.columns)


def hline(row, color='black', width='1px'):
    return [f'border-bottom: {width} solid {color};' for _ in row]


def pp(X: pd.DataFrame, float_format: str = None, h_subset=None) -> Styler:
    """Pretty print pandas dataframe with ability to stroke some cells"""

    if float_format is None:
        float_format = pd.options.display.float_format
    if float_format is None:
        float_format = '{:,.2f}'
    x = X.style.format(float_format).apply(background, axis=None)
    return x if h_subset is None else x.apply(hline, axis=1, subset=h_subset)
