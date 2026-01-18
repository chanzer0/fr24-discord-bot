from .help import register as register_help
from .set_notify_channel import register as register_set_notify_channel
from .subscribe import register as register_subscribe
from .unsubscribe import register as register_unsubscribe


def setup_commands(tree, db, config) -> None:
    register_set_notify_channel(tree, db, config)
    register_subscribe(tree, db, config)
    register_unsubscribe(tree, db, config)
    register_help(tree, db, config)
