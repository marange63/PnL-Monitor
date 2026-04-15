import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import squarify

from constants import SOURCE_COLORS, MULTI_SOURCE_COLOR, PNL_POS_COLOR, PNL_NEG_COLOR

_RG_CMAP = mcolors.LinearSegmentedColormap.from_list(
    "pnl_rg", [PNL_NEG_COLOR, PNL_POS_COLOR])

dollar_fmt = plt.FuncFormatter(lambda x, _: f"${x:,.0f}")
pct_fmt = plt.FuncFormatter(lambda x, _: f"{x * 100:+.2f}%")


def draw_treemap(ax, df, grouped=False):
    """Draw a treemap sized by SOD VALUE, colored by % move (RdYlGn).
    Returns (rects, plot_data) for hover hit-testing, or ([], empty_df) if no data.
    """
    ax.clear()
    ax.set_axis_off()

    if grouped:
        agg = (df.groupby('Ticker Alias').agg(
                PnL=('PnL', 'sum'),
                SOD_VALUE=('SOD VALUE', 'sum'),
            ).reset_index()
              .rename(columns={'SOD_VALUE': 'SOD VALUE'}))
        agg['pct_move'] = agg['PnL'] / agg['SOD VALUE']
        plot_data = agg
    else:
        plot_data = (df[['Ticker Alias', 'SOD VALUE', 'PnL', '% Move On Day']]
                     .dropna()
                     .rename(columns={'% Move On Day': 'pct_move'})
                     .reset_index(drop=True))

    plot_data = (plot_data[plot_data['PnL'].notna()]
                 .assign(abs_pnl=lambda d: d['PnL'].abs())
                 .query('abs_pnl > 0')
                 .sort_values('abs_pnl', ascending=False)
                 .reset_index(drop=True))
    if plot_data.empty:
        return [], plot_data

    fig_w, fig_h = ax.figure.get_size_inches()
    sizes = squarify.normalize_sizes(plot_data['abs_pnl'].tolist(), fig_w, fig_h)
    rects = squarify.squarify(sizes, 0, 0, fig_w, fig_h)

    pct_moves = plot_data['pct_move'].tolist()
    max_abs = max(max(abs(p) for p in pct_moves), 1e-6)
    cmap = _RG_CMAP
    norm = plt.Normalize(vmin=-max_abs, vmax=max_abs)

    for rect, color, (_, row) in zip(rects, [cmap(norm(p)) for p in pct_moves],
                                     plot_data.iterrows()):
        ax.add_patch(plt.Rectangle(
            (rect['x'], rect['y']), rect['dx'], rect['dy'],
            facecolor=color, edgecolor='white', linewidth=1.5, zorder=1))
        if min(rect['dx'], rect['dy']) > fig_w * 0.06:
            ax.text(rect['x'] + rect['dx'] / 2, rect['y'] + rect['dy'] / 2,
                    f"{row['Ticker Alias']}\n{row['pct_move'] * 100:+.1f}%",
                    ha='center', va='center', fontsize=7, fontweight='bold',
                    color='black', clip_on=True, zorder=2)

    ax.set_xlim(0, fig_w)
    ax.set_ylim(fig_h, 0)  # invert y so squarify's origin is upper-left
    ax.add_patch(plt.Rectangle((0, 0), 1, 1, fill=False, edgecolor='black',
                                linewidth=1.5, transform=ax.transAxes,
                                clip_on=False, zorder=10))
    return rects, plot_data.reset_index(drop=True)


def build_grouped_scatter_df(df):
    """Collapse per-position rows into one row per Ticker Alias, summing PnL and SOD VALUE."""
    agg = df.groupby('Ticker Alias').agg(
        PnL=('PnL', 'sum'),
        SOD_VALUE=('SOD VALUE', 'sum'),
        Sources=('Source', lambda x: ', '.join(sorted(x.unique())))
    ).reset_index()
    agg = agg.rename(columns={'SOD_VALUE': 'SOD VALUE'})
    agg['Return'] = agg['PnL'] / agg['SOD VALUE']
    return agg


def draw_scatter(ax, df, log_x=False, grouped=False, return_mode=False):
    """Draw scatter plot. Returns the DataFrame that was plotted (may be grouped)."""
    ax.clear()
    if grouped:
        plot_data = build_grouped_scatter_df(df)
        y_vals = plot_data['Return'] if return_mode else plot_data['PnL']
        colors = plot_data['Sources'].apply(
            lambda s: SOURCE_COLORS.get(s, MULTI_SOURCE_COLOR))
        ax.scatter(plot_data['SOD VALUE'], y_vals, c=colors,
                   alpha=0.7, edgecolors='white', linewidths=0.5)
        for ticker, sod, y in zip(plot_data['Ticker Alias'], plot_data['SOD VALUE'], y_vals):
            ax.annotate(ticker, (sod, y), fontsize=8.5, fontweight='bold',
                        textcoords="offset points", xytext=(4, 4))
    else:
        plot_data = df
        y_vals = df['% Move On Day'] if return_mode else df['PnL']
        colors = df['Source'].map(SOURCE_COLORS)
        ax.scatter(df['SOD VALUE'], y_vals, c=colors, alpha=0.7,
                   edgecolors='white', linewidths=0.5)
        for ticker, sod, y in zip(df['Ticker Alias'], df['SOD VALUE'], y_vals):
            ax.annotate(ticker, (sod, y), fontsize=8.5, fontweight='bold',
                        textcoords="offset points", xytext=(4, 4))
    ax.set_facecolor('white')
    ax.set_axisbelow(True)
    ax.grid(True, color='#e8e8e8', linewidth=0.5)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#cccccc')
    ax.spines['bottom'].set_color('#cccccc')
    ax.axhline(0, color='#aaaaaa', linewidth=0.8, linestyle='--')
    xlabel = "SOD VALUE ($)  [log scale]" if log_x else "SOD VALUE ($)"
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Return (%)" if return_mode else "PnL ($)")
    ax.xaxis.set_major_formatter(dollar_fmt)
    ax.yaxis.set_major_formatter(pct_fmt if return_mode else dollar_fmt)
    ax.xaxis.set_major_locator(plt.MaxNLocator(nbins=6, prune='both'))
    if log_x:
        ax.set_xscale('log')
    return plot_data.reset_index(drop=True)


def build_bar_df(df, sort_by_name=False, grouped=True, return_mode=False):
    """Build the DataFrame for the bar chart.

    grouped=True  → one bar per Ticker Alias (values summed across sources)
    grouped=False → one bar per position; label = 'TICKER (Source)'
    return_mode   → Value column = PnL/SOD VALUE (decimal); else PnL ($)
    Always adds 'Label', 'Source', and 'Value' columns.
    """
    if grouped:
        bar_df = (
            df[['Ticker Alias', 'PnL', 'SOD VALUE']]
            .dropna()
            .groupby('Ticker Alias', as_index=False)
            .agg({'PnL': 'sum', 'SOD VALUE': 'sum'})
        )
        bar_df['Label'] = bar_df['Ticker Alias']
        bar_df['Source'] = None
        bar_df['Value'] = bar_df['PnL'] / bar_df['SOD VALUE'] if return_mode else bar_df['PnL']
    else:
        bar_df = df[['Ticker Alias', 'Source', 'PnL', 'SOD VALUE', '% Move On Day']].dropna().copy()
        bar_df['Label'] = bar_df['Ticker Alias'] + ' (' + bar_df['Source'] + ')'
        bar_df['Value'] = bar_df['% Move On Day'] if return_mode else bar_df['PnL']

    if sort_by_name:
        bar_df = bar_df.sort_values('Label', ascending=False)
    else:
        bar_df = bar_df.sort_values('Value', key=abs, ascending=True)
    return bar_df.reset_index(drop=True)


def build_tag_bar_df(df, sort_by_name=False):
    """Group PnL by Tag. Always grouped; ignores Group Tickers toggle."""
    bar_df = (
        df[['Tag', 'PnL']]
        .dropna()
        .groupby('Tag', as_index=False)
        .agg({'PnL': 'sum'})
    )
    bar_df['Label'] = bar_df['Tag']
    bar_df['Value'] = bar_df['PnL']
    if sort_by_name:
        bar_df = bar_df.sort_values('Label', ascending=False)
    else:
        bar_df = bar_df.sort_values('Value', key=abs, ascending=True)
    return bar_df.reset_index(drop=True)


def draw_bar(ax_bar, bar_df, return_mode=False):
    bar_colors = [PNL_NEG_COLOR if v < 0 else PNL_POS_COLOR for v in bar_df['Value']]
    ax_bar.clear()
    ax_bar.barh(bar_df['Label'], bar_df['Value'], color=bar_colors,
                edgecolor='black', linewidth=0.5)
    ax_bar.set_facecolor('white')
    ax_bar.set_axisbelow(True)
    ax_bar.grid(True, axis='x', color='#e8e8e8', linewidth=0.5)
    ax_bar.spines['top'].set_visible(False)
    ax_bar.spines['right'].set_visible(False)
    ax_bar.spines['left'].set_color('#cccccc')
    ax_bar.spines['bottom'].set_color('#cccccc')
    ax_bar.axvline(0, color='black', linewidth=0.8, linestyle='-')
    ax_bar.tick_params(axis='y', labelsize=7)
    ax_bar.set_xlabel("Return (%)" if return_mode else "PnL ($)")
    ax_bar.xaxis.set_major_formatter(pct_fmt if return_mode else dollar_fmt)
    ax_bar.xaxis.set_major_locator(plt.MaxNLocator(nbins=4, prune='both'))
    ax_bar.margins(y=0.01, x=0.0)

    for bar in ax_bar.patches:
        w = bar.get_width()
        y = bar.get_y() + bar.get_height() / 2
        label = f"{w * 100:+.2f}%" if return_mode else f"${w:,.0f}"
        if w >= 0:
            ax_bar.annotate(label, xy=(w, y),
                            xytext=(4, 0), textcoords="offset points",
                            va='center', ha='left', fontsize=7)
        else:
            ax_bar.annotate(label, xy=(w, y),
                            xytext=(-4, 0), textcoords="offset points",
                            va='center', ha='right', fontsize=7)

    # Expand x-limits by 30% on whichever side has labels so they don't clip
    x0, x1 = ax_bar.get_xlim()
    span = x1 - x0
    ax_bar.set_xlim(x0 - span * 0.30, x1 + span * 0.30)
