"""A provider in credential-exhaustion cooldown stays visible in pickers.

``list_authenticated_providers(for_picker=True)`` deliberately keeps a
provider whose credential pool exists but is entirely in exhaustion cooldown
(every key rate-limited or out of credit). Cooldowns are transient and often
per-model, so hiding the provider strands the user: the provider *and its
whole model list* disappear from the picker, leaving nothing to select back
into once the cooldown lifts.

That flag defaults to ``False`` because programmatic resolution paths do want
availability semantics. The recurring bug is that human-facing surfaces forget
to opt in. It has now been fixed per-call-site three times:

- #52642 (@deepjia) — aux picker dropped user ``providers:`` entries.
- #66624 (@Drexuxux) — aux picker hid rate-limited pools.
- this file — the *main* pickers (dashboard/TUI/API ``build_model_options_
  payload``, the CLI ``/model`` no-args picker, the TUI gateway
  ``model.options`` method, and the kanban dashboard config screen) all still
  omitted it, so a single OpenRouter key that took a 402 erased OpenRouter and
  all 34 of its models from every config screen at once.

These tests guard the seam rather than any one kwarg list: each human-facing
entry point must forward ``for_picker=True``.
"""

from unittest.mock import patch

import pytest

from hermes_cli import inventory


def _ctx():
    """An empty context — these tests assert on forwarded kwargs, not rows."""
    return inventory.ConfigContext(
        current_provider="",
        current_model="",
        current_base_url="",
        user_providers={},
        custom_providers=[],
    )


@pytest.fixture
def spy_payload():
    """Patch build_models_payload and capture the kwargs it was called with."""
    with patch.object(inventory, "build_models_payload") as spy:
        spy.return_value = {"providers": [], "model": "", "provider": ""}
        yield spy


def test_model_options_payload_opts_into_picker_visibility(spy_payload):
    """The shared dashboard/TUI/API picker payload must set for_picker."""
    inventory.build_model_options_payload(_ctx())

    assert spy_payload.call_args.kwargs["for_picker"] is True


@pytest.mark.parametrize("refresh", [False, True])
def test_model_options_payload_keeps_picker_visibility_on_refresh(
    spy_payload, refresh
):
    """An explicit refresh must not quietly drop back to availability gating."""
    inventory.build_model_options_payload(_ctx(), refresh=refresh)

    assert spy_payload.call_args.kwargs["for_picker"] is True


def test_aux_picker_rows_opt_into_picker_visibility(spy_payload):
    """The aux-picker entry point keeps the behaviour #66624 restored."""
    inventory.build_aux_picker_rows()

    assert spy_payload.call_args.kwargs["for_picker"] is True


def test_exhausted_pool_provider_survives_the_picker_listing():
    """Behavioural check at the substrate: a pool with credentials but zero
    available entries is hidden by default and kept for a picker."""
    from hermes_cli import model_switch

    class _AllExhausted:
        def has_credentials(self):
            return True

        def has_available(self):
            return False

    with patch("agent.credential_pool.load_pool", return_value=_AllExhausted()):
        assert model_switch._credential_pool_is_usable("openrouter") is False
        # raw_pool_present must not resurrect it — a real pool's availability
        # state is authoritative. Picker visibility is layered on top of this
        # in list_authenticated_providers(), not smuggled in here.
        assert (
            model_switch._credential_pool_is_usable(
                "openrouter", raw_pool_present=True
            )
            is False
        )
