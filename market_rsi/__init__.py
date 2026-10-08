"""Market RSI source-checkout interface; native bound modules stay in place."""


def __getattr__(name):
    """Keep legacy helper imports bound to their original source implementation."""
    from research.market_rsi import market_rsi as legacy

    return getattr(legacy, name)
