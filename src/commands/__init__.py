from .help import register as register_help
from .refresh_reference import register as register_refresh_reference
from .set_notify_channel import register as register_set_notify_channel
from .subscribe import register as register_subscribe
from .unsubscribe import register as register_unsubscribe


def setup_commands(tree, db, config, fr24, reference_data) -> None:
    register_set_notify_channel(tree, db, config)
    register_subscribe(tree, db, config, reference_data)
    register_unsubscribe(tree, db, config, reference_data)
    register_refresh_reference(tree, db, config, reference_data)
    register_help(tree, db, config)
