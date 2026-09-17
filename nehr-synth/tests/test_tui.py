import asyncio

from textual.widgets import Button, DataTable, Input, Static, TabbedContent, TextArea

from nehr_synth.app import SynthApp
from nehr_synth.runtime import read_json


async def press_button(app, pilot, name):
    button = app.screen.query_one("#" + name, Button)
    button.scroll_visible(immediate=True)
    await pilot.pause()
    button.focus()
    await pilot.pause(0.3)
    await pilot.press("enter")
    await pilot.pause(0.3)


async def test_form_generation_inspection_export(config, fake_validator, tmp_path):
    app = SynthApp(config)
    async with app.run_test(size=(100, 38)) as pilot:
        app.query_one("#patients", Input).value = "0"
        await press_button(app, pilot, "generate")
        assert "positive" in str(app.query_one("#form-error", Static).render())
        app.query_one("#patients", Input).value = "4"
        await press_button(app, pilot, "generate")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert not app.busy
        assert read_json(app.current_run / "manifest.json")["counts"] == {"Patient": 4}
        await press_button(app, pilot, "inspect-result")
        assert app.query_one("#patients-table", DataTable).row_count == 4
        app.query_one("#patients-table", DataTable).focus()
        await pilot.press("enter")
        assert '"resourceType": "Patient"' in app.query_one("#json", TextArea).text
        app.query_one("#search", Input).value = "no-such-patient"
        await pilot.pause()
        assert app.query_one("#patients-table", DataTable).row_count == 0
        app.query_one("#export-path", Input).value = str(tmp_path / "export")
        await press_button(app, pilot, "export")
        assert (tmp_path / "export" / "manifest.json").exists()
        await press_button(app, pilot, "browse")
        await pilot.resize_terminal(80, 24)
        await pilot.press("f1")


async def test_save_load_settings(config, tmp_path):
    app = SynthApp(config)
    async with app.run_test(size=(100, 40)) as pilot:
        path = tmp_path / "ui.toml"
        app.query_one("#config-path", Input).value = str(path)
        await press_button(app, pilot, "save")
        app.query_one("#patients", Input).value = "9"
        await press_button(app, pilot, "load")
        assert app.query_one("#patients", Input).value == "3"
        await press_button(app, pilot, "settings")
        app.screen.query_one("#setting-passport_width", Input).value = "8"
        await press_button(app, pilot, "apply-settings")
        assert app.config.passport_width == 8


async def test_cancel_worker_keeps_ui_responsive(config, monkeypatch, fake_validator):
    import nehr_synth.pipeline as pipeline

    original = pipeline.demographics

    def slow(c, **kwargs):
        kwargs["cancel"].event.wait(30)
        return original(c, **kwargs)

    monkeypatch.setattr(pipeline, "demographics", slow)
    app = SynthApp(config)
    async with app.run_test(size=(100, 40)) as pilot:
        await press_button(app, pilot, "generate")
        assert app.busy
        await pilot.press("escape")
        await app.workers.wait_for_complete()
        await asyncio.sleep(0)
        assert read_json(app.current_run / "manifest.json")["status"] == "incomplete"
        assert not app.busy
        assert app.query_one("#tabs", TabbedContent).active == "progress-tab"
        await press_button(app, pilot, "inspect-result")
        assert "Cancelled" in app.query_one("#json", TextArea).text
