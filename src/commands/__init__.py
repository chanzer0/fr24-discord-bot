from .help import register as register_help
from .set_notify_channel import register as register_set_notify_channel
from .subscribe import register as register_subscribe
from .unsubscribe import register as register_unsubscribe
from .usage import register as register_usage


def setup_commands(tree, db, config, fr24) -> None:
    register_set_notify_channel(tree, db, config)
    register_subscribe(tree, db, config)
    register_unsubscribe(tree, db, config)
    register_usage(tree, db, config, fr24)
    register_help(tree, db, config)
