import pandas as pd
import numpy as np
import re
from numpy.typing import NDArray
from inspect import getfullargspec
from itertools import repeat, zip_longest
from ipywidgets import widgets, interactive, HBox, VBox
from ipyslickgrid import show_grid

from simple.types import TPairTrade
from simple.pretty import iterable
from simple.backtest import getProfit

import plotly.graph_objs as go
from plotly.graph_objs.scattergl import Marker, Line
from plotly.subplots import make_subplots
from plotly_resampler import FigureWidgetResampler, EfficientLTTB


# default chart figure parameters
default_template = 'plotly_white'
default_height = 600
default_margin = dict(l=45, r=15, b=10, t=30, pad=3)
default_legend = dict(x=0.1, y=1, orientation="h")

default_styles = {
    'Tick': dict(color='gray', opacity=0.25),
    'Ask': dict(color='red', opacity=0.25),
    'Bid': dict(color='green', opacity=0.25),
    'qA': dict(color='red', opacity=0.5, dash='dot'),
    'qB': dict(color='green', opacity=0.5, dash='dot'),
    
    'Signal': dict(color='blue', opacity=0.5, row=2),
    
    'MidPnL': dict(color='darkgray', width=2, opacity=0.4, secondary_y=True, shape='hv', connectgaps=True),
    'RawPnL': dict(color='gray', width=2, opacity=0.4, secondary_y=True, shape='hv', connectgaps=True),
    'Profit': dict(color='blue', width=3, opacity=0.5, secondary_y=True, shape='hv', connectgaps=True),
    
    'EnterLong': dict(mode='markers', marker=dict(symbol='triangle-up', size=6, color='green', line_color='darkgreen', line_width=1)),
    'ExitLong': dict(mode='markers', marker=dict(symbol='x', size=5, color='green', line_color='darkgreen', line_width=1)),
    'EnterShort': dict(mode='markers', marker=dict(symbol='triangle-down', size=6, color='red', line_color='darkred', line_width=1)),
    'ExitShort': dict(mode='markers', marker=dict(symbol='x', size=5, color='red', line_color='darkred', line_width=1))
}

# default grid parameters
grid_options = {
    'editable': False,
    'forceFitColumns': True,
    'multiSelect': False,
    'rowHeight': 26,
    'maxVisibleRows': 6
}


def addLines(fig: go.FigureWidget, **lines):
    """Add line(s) or linestyle(s) to the figure"""

    for line_name in lines:
        line = lines[line_name]
        if type(line) != dict:
            line = {'hf_y': line}  # if there is only one value specified - interpret as Y series
            
        # if predefined name specified - fill missed attributes from default_styles
        line = {**default_styles.get(line_name, {}), **line}
            
        # layout parameters can be redefined in the 'lines' parameters also
        if line_name == 'layout':
            for param_name in line:
                fig.layout[param_name] = line[param_name]
        else:
            if line.get('mode') == 'markers':
                line_class = Marker
            elif line.get('mode') == 'candlestick':
                line_class = go.Candlestick
            else:
                line_class = Line

            trace_dict = {}  # parameters not belong to the Line will be moved to upper-levels
            scatter_dict = {}
            line_dict = {}
            for param in line:
                if param in getfullargspec(line_class).args:
                    line_dict[param] = line[param]
                elif param in getfullargspec(go.Scattergl).args:
                    scatter_dict[param] = line[param]
                else:
                    trace_dict[param] = line[param]

            name = 'marker' if line_class == go.scattergl.Marker else 'line'
            if len(line_dict) > 0:
                scatter_dict[name] = line_dict
            if 'row' in trace_dict and 'col' not in trace_dict:
                trace_dict['col'] = 1

            if line_class == go.Candlestick:
                if 'x' not in line_dict:
                    line_dict['x'] = np.arange(len(line_dict['open']))
                fig.add_candlestick(name=line_name, **line_dict)
            else:
                fig.add_trace(go.Scattergl(name=line_name, **scatter_dict), limit_to_view=True, **trace_dict)


def getRowCount(**lines) -> int:
    """Calculated rowcount based on max 'row=x' parameter values"""
    row_count = 1
    for value in lines.values():
        if isinstance(value, dict) and 'row' in value:
            row_count = max(row_count, value['row'])
    return row_count


def chartFigure(height: int = default_height, rows: int = 1, title: str = None,
                template: str = default_template, equal: bool = False,
                **lines) -> go.FigureWidget:
    """Create interactive dynamic chart widget with horizontal subplots"""

    rows = max(getRowCount(**lines), rows)
    if rows > 1:
        k = 0.5 if equal else 0.1 + 0.1 * rows
        row_heights = [1 - k] + list(repeat(k / (rows - 1), rows - 1))
    else:
        row_heights = None

    specs = list(repeat([{"secondary_y": True}], rows))
    fig = FigureWidgetResampler(
        go.FigureWidget(make_subplots(rows=rows, cols=1, row_heights=row_heights,
                                      vertical_spacing=0.03, shared_xaxes=True, specs=specs)),
        default_downsampler=EfficientLTTB(interleave_gaps=False)
    )

    fig.update_layout(autosize=True, height=height, template=template, title=title,
                      legend=default_legend, margin=default_margin)

    if lines is not None:
        addLines(fig, **lines)

    if rows > 1:
        fig.update_xaxes(spikemode='across+marker', spikedash='dot', spikethickness=2, spikesnap='cursor')
        fig.update_traces(xaxis=f'x{rows}')

    for i in range(rows, 0, -1):  # disable all range sliders
        fig.update_xaxes(row=i, col=1, rangeslider_visible=False)

    return fig


def updateFigure(fig: go.FigureWidget, **lines):
    """Update lines values"""

    # strip html tags and some others auxiliary marks
    names = [re.sub('<[^<]+?>|\[.*]|~.*|\s', '', s.name) for s in fig.data]
    with fig.batch_update():
        # update existing lines
        for name, line in lines.items():
            y = line['y'] if type(line) == dict else line
            if name in names:
                k = names.index(name)
                fig.hf_data[k]['x'] = line.get('x', np.arange(len(y))) if type(line) == dict else np.arange(len(y))
                fig.hf_data[k]['y'] = y

            elif not name.startswith('_') and iterable(y):
                # add a new one if it doesn't already exist and has non-prefixed name
                addLines(fig, **{name: line})

        if len(fig.data) > 0:
            fig.reload_data()

        # layout can be specified in lines also
        layout = lines.get('layout')
        if layout is not None:
            for param_name in layout:
                fig.layout[param_name] = layout[param_name]

        fig.update_traces(xaxis='x1')


def updateSliders(sliders: widgets, **values: dict):
    """Update slider values"""

    for slider in sliders:
        slider.value = values[slider.description]


def interactFigure(model: callable, height: int = default_height, rows: int = 1,
                   title: str = None, template: str = default_template,
                   **lines) -> widgets:
    """Interactive chart with model's internal data-series and sliders to change parameters"""

    spec = getfullargspec(model)
    x = dict(zip_longest(reversed(spec.args), [] if spec.defaults is None else reversed(spec.defaults), fillvalue=1))
    defaults = dict(reversed(x.items()))
    fig = chartFigure(height=height, rows=rows, template=template, title=title, **lines)

    def update(**arg):
        updateFigure(fig, **model(**arg))

    sliders = interactive(update, **defaults).children[:-1]

    # first run with initial values
    param = {s.description: s.value for s in sliders}
    update(**param)

    return VBox([HBox(sliders), fig])


def interactTable(model: callable, X: pd.DataFrame, height: int = default_height, rows: int = 1,
                  template: str = default_template, **lines) -> widgets:
    """Interactive parameter table browser"""

    box = interactFigure(model, height=height, rows=rows, template=template, **lines)

    def on_changed(event, grid):
        changed = grid.get_changed_df().reset_index()
        k = event['new'][0]
        selected = changed.iloc[k:k + 1].to_dict('records')[0]
        param = dict(filter(lambda x: x[0] in getfullargspec(model).args, selected.items()))

        sliders, fig = box.children[0].children, box.children[1]
        with fig.batch_update():
            updateSliders(sliders, **param)
            updateFigure(fig, **model(**param))

    grid = show_grid(X, grid_options=grid_options, column_options={'defaultSortAsc': False})
    grid.on('selection_changed', on_changed)

    return VBox([box, grid])


def chartProfit(trades: NDArray[TPairTrade], use_time: bool = False) -> dict:
    """Returns dict with profit lines and trades"""

    P = getProfit(trades)
    x = P.DateTime if use_time else P.Index
    
    return {
        'Profit': dict(x=x, y=P.Profit.cumsum()),
        'MidPnL': dict(x=x, y=P.MidPnL.cumsum())
    }


def chartTrades(trades: NDArray[TPairTrade], use_time: bool = False) -> dict:
    """Returns dict with trades symbols"""
    Long = trades[trades.Size > 0]
    Short = trades[trades.Size < 0]

    return {
        'EnterLong': dict(x=Long.T0 if use_time else Long.X0, y=Long.Price0),
        'ExitLong': dict(x=Long.T1 if use_time else Long.X1, y=Long.Price1),
        'EnterShort': dict(x=Short.T0 if use_time else Short.X0, y=Short.Price0),
        'ExitShort': dict(x=Short.T1 if use_time else Short.X1, y=Short.Price1)
    }


def chartParallel(X: pd.DataFrame, height: int = 400, inverse: list = []) -> widgets:
    """Parallel coordinates plot for optimization results"""

    x = X.reset_index()    # include index columns too
    dimensions = [
        {'label': c,
         'values': x[c],
         'range': (x[c].max(), x[c].min()) if c in inverse else (x[c].min(), x[c].max())
        } for c in x.columns
    ]

    fig = go.FigureWidget(data=go.Parcoords(dimensions=dimensions))
    fig.update_layout(autosize=True, height=height, template=default_template,
                      margin=dict(l=45, r=45, b=20, t=50, pad=3))
    return fig
