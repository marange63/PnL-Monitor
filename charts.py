import matplotlib.pyplot as plt

from constants import SOURCE_COLORS, MULTI_SOURCE_COLOR, PNL_POS_COLOR, PNL_NEG_COLOR

dollar_fmt = plt.FuncFormatter(lambda x, _: f"${x:,.0f}")


def build_grouped_scatter_df(df):
    """Collapse per-position rows into one row per Ticker Alias, summing PnL and SOD VALUE."""
    agg = df.groupby('Ticker Alias').agg(
        PnL=('PnL', 'sum'),
        SOD_VALUE=('SOD VALUE', 'sum'),
        Sources=('Source', lambda x: ', '.join(sorted(x.unique())))
    ).reset_index()
    return agg.rename(columns={'SOD_VALUE': 'SOD VALUE'})


def draw_scatter(ax, df, log_x=False, grouped=False):
    """Draw scatter plot. Returns the DataFrame that was plotted (may be grouped)."""
    ax.clear()
    if grouped:
        plot_data = build_grouped_scatter_df(df)
        colors = plot_data['Sources'].apply(
            lambda s: SOURCE_COLORS.get(s, MULTI_SOURCE_COLOR))
        ax.scatter(plot_data['SOD VALUE'], plot_data['PnL'], c=colors,
                   alpha=0.7, edgecolors='white', linewidths=0.5)
        for ticker, sod, pnl in zip(
                plot_data['Ticker Alias'], plot_data['SOD VALUE'], plot_data['PnL']):
            ax.annotate(ticker, (sod, pnl), fontsize=7,
                        textcoords="offset points", xytext=(4, 4))
    else:
        plot_data = df
        colors = df['Source'].map(SOURCE_COLORS)
        ax.scatter(df['SOD VALUE'], df['PnL'], c=colors, alpha=0.7,
                   edgecolors='white', linewidths=0.5)
        for ticker, sod, pnl in zip(df['Ticker Alias'], df['SOD VALUE'], df['PnL']):
            ax.annotate(ticker, (sod, pnl), fontsize=7,
                        textcoords="offset points", xytext=(4, 4))
    ax.axhline(0, color='gray', linewidth=0.8, linestyle='--')
    xlabel = "SOD VALUE ($)  [log scale]" if log_x else "SOD VALUE ($)"
    ax.set_xlabel(xlabel)
    ax.set_ylabel("PnL ($)")
    ax.xaxis.set_major_formatter(dollar_fmt)
    ax.yaxis.set_major_formatter(dollar_fmt)
    ax.xaxis.set_major_locator(plt.MaxNLocator(nbins=6, prune='both'))
    if log_x:
        ax.set_xscale('log')
    return plot_data.reset_index(drop=True)


def build_bar_df(df, sort_by_name=False):
    bar_df = (
        df[['Ticker Alias', 'PnL']]
        .dropna()
        .groupby('Ticker Alias', as_index=False)['PnL']
        .sum()
    )
    if sort_by_name:
        bar_df = bar_df.sort_values('Ticker Alias', ascending=False)
    else:
        bar_df = bar_df.sort_values('PnL', key=abs, ascending=True)
    return bar_df.reset_index(drop=True)


def draw_bar(ax_bar, bar_df):
    bar_colors = [PNL_NEG_COLOR if p < 0 else PNL_POS_COLOR for p in bar_df['PnL']]
    ax_bar.clear()
    ax_bar.barh(bar_df['Ticker Alias'], bar_df['PnL'], color=bar_colors,
                edgecolor='black', linewidth=0.5)
    ax_bar.axvline(0, color='gray', linewidth=0.8, linestyle='--')
    ax_bar.set_xlabel("PnL ($)")
    ax_bar.xaxis.set_major_formatter(dollar_fmt)
    ax_bar.xaxis.set_major_locator(plt.MaxNLocator(nbins=4, prune='both'))
    ax_bar.set_facecolor("#f8f8f8")
    ax_bar.margins(y=0.01, x=0.18)

    for bar in ax_bar.patches:
        w = bar.get_width()
        y = bar.get_y() + bar.get_height() / 2
        if w >= 0:
            ax_bar.annotate(f"${w:,.0f}", xy=(w, y),
                            xytext=(4, 0), textcoords="offset points",
                            va='center', ha='left', fontsize=7)
        else:
            ax_bar.annotate(f"${w:,.0f}", xy=(w, y),
                            xytext=(-4, 0), textcoords="offset points",
                            va='center', ha='right', fontsize=7)
