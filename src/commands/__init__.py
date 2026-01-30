from .help import register as register_help
from .info import register as register_info
from .logs import register as register_logs
from .credits_remaining import register as register_credits_remaining
from .key_parking import register as register_key_parking
from .my_subs import register as register_my_subs
from .polling import register as register_polling
from .filterlist import register as register_filterlist
from .refresh_reference import register as register_refresh_reference
from .set_change_roles import register as register_set_change_roles
from .set_notify_channel import register as register_set_notify_channel
from .subscribe import register as register_subscribe
from .unsubscribe import register as register_unsubscribe


def setup_commands(tree, db, config, fr24, reference_data, poller_state) -> None:
    register_set_notify_channel(tree, db, config)
    register_set_change_roles(tree, db, config)
    register_subscribe(tree, db, config, reference_data)
    register_unsubscribe(tree, db, config, reference_data)
    register_refresh_reference(tree, db, config, reference_data)
    register_credits_remaining(tree, db, config)
    register_key_parking(tree, db, config, fr24)
    register_my_subs(tree, db, config, reference_data)
    register_polling(tree, db, config, poller_state)
    register_info(tree, db, config, reference_data)
    register_filterlist(tree, db, config)
    register_logs(tree, db, config)
    register_help(tree, db, config)
