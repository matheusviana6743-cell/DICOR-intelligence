"""Runtime compatibility hooks for CENTRAL LASTRO."""
import flask

_original_url_for = flask.url_for
_original_render_template_string = flask.render_template_string


def _url_for(endpoint, **values):
    # The legacy navigation asks for an `actions` index endpoint that the
    # current app does not define. Keep the dashboard usable without changing
    # the action-detail endpoint (`action`, which requires action_id).
    if endpoint == "actions" and "action_id" not in values:
        return "/actions"
    try:
        return _original_url_for(endpoint, **values)
    except Exception:
        if endpoint == "actions":
            return "/actions"
        raise


def _render(*args, **kwargs):
    return _original_render_template_string(*args, **kwargs)


flask.url_for = _url_for
flask.render_template_string = _render
