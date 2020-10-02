import os
import logging
import toml
import sass
from markupsafe import Markup
from dashmachine.dm.file_watcher import FileWatcher
from dashmachine.paths import (
    root_folder,
    dashboards_folder,
    settings_toml,
    data_sources_toml,
    shared_cards_toml,
    users_toml,
    system_themes_folder,
    custom_themes_folder,
    static_folder,
    user_platform,
    user_templates_folder,
    user_markdown_folder,
)
from dashmachine.dm.config_modifier import ConfigModifier
from dashmachine.dm.settings import Settings
from dashmachine.dm.dashboard import Dashboard
from dashmachine.dm.data_source_handler import DataSourceHandler
from dashmachine.dm.utils import DEFAULT_QUERY_PROVIDERS


class DashMachine:
    def __init__(self, app):
        """
        The DashMachine class. This is the core of DashMachine, it serves as as a
        scaffold for all of the classes that make up DashMachine's functionality.
        It is responsible for initializing all of the classes that hold the data
        from the files in /config, and watching those config files for changes.
        When this class detects a change in a file, it rebuilds whatever it needs
        to, to make sure the interface is updated properly.

        This class is also responsible for running the functions that handle custom
        themes.

        Some DashMachine configurations are applied in the html template
        rendered when the main page loads. The ways in which these
        configurations effect page's appearance can be found
        in /dashmachine/templates/main/main.html

        :param app: (Flask Application Object) see:
        https://flask.palletsprojects.com/en/1.1.x/quickstart/

        """
        logging.info("DashMachine starting..")
        self.app = app
        self.query_providers = DEFAULT_QUERY_PROVIDERS
        self.users = None
        self.config_modifier = ConfigModifier()
        self.settings = None
        self.data_source_handler = None
        self.dashboards = None
        self.main_dashboard = None
        self.shared_cards = []
        self.build()

        logging.info("File watchers starting..")
        self.settings_file_watcher = FileWatcher(settings_toml, self.build)
        self.dashboards_folder_watcher = FileWatcher(
            dashboards_folder, self.build, event="added"
        )
        self.data_sources_file_watcher = FileWatcher(data_sources_toml, self.build)
        self.shared_cards_file_watcher = FileWatcher(shared_cards_toml, self.build)
        self.users_file_watcher = FileWatcher(users_toml, self.build)
        self.custom_themes_watcher = FileWatcher(
            custom_themes_folder, self.build, event="all"
        )
        self.platform_folder_watcher = FileWatcher(
            user_platform, self.build, event="all"
        )
        self.user_templates_folder_watcher = FileWatcher(
            user_templates_folder, self.build, event="all"
        )
        self.user_markdown_folder_watcher = FileWatcher(
            user_markdown_folder, self.build, event="all"
        )
        self.dashboard_file_watchers = []
        for dboard_name, dboard in self.dashboards.items():
            self.dashboard_file_watchers.append(
                FileWatcher(dboard.toml_path, dboard.load_cards)
            )

    def build(self):
        """
        This method rebuilds the entire App, it is called when the file watchers detect
        a change that requires the entire application to be rebuilt.

        :return:
        """
        # clear out any errors being held by objects
        self.config_modifier.error = None

        # load settings
        self.settings = Settings()
        if hasattr(self.settings, "query_providers"):
            self.query_providers = self.settings.query_providers
        else:
            self.query_providers = DEFAULT_QUERY_PROVIDERS

        # compile theme
        self.compile_theme()

        # load data_source handler
        self.data_source_handler = DataSourceHandler()

        # load shared cards
        self.shared_cards = self.load_shared_cards()

        # load dashboards
        self.dashboards = {}
        for file in os.listdir(dashboards_folder):
            self.dashboards[file.replace(".toml", "")] = Dashboard(file=file, dm=self)

        # pass any errors to the dashboards
        if self.settings.error:
            for dboard_name, dboard in self.dashboards.items():
                dboard.error = self.settings.error
            self.settings = Settings(read_toml=False)
        if self.data_source_handler.error:
            for dboard_name, dboard in self.dashboards.items():
                dboard.error = self.data_source_handler.error

        logging.info("DashMachine built")

    def get_dashboard_by_name(self, name):
        """
        Get the dashboard object with a given name. See dm/dashboard.py for docs on
        the dashboard object

        :param name: (str) the name of the dashboard, e.g. 'main'
        :return:
        """
        return (
            self.dashboards[name] if self.dashboards.get(name) else self.main_dashboard
        )

    def compile_theme(self):
        """
        Uses libsass-python to compile the theme and replace the bootstrap.min.css file
        The theme name is set by settings object. See dm/settings.py for docs on the
        settings object.

        Documentation: https://sass.github.io/libsass-python/

        :return:
        """
        if f"{self.settings.theme}.scss" in os.listdir(custom_themes_folder):
            theme_scss_file = os.path.join(
                custom_themes_folder, f"{self.settings.theme}.scss"
            )
        else:
            theme_scss_file = os.path.join(
                system_themes_folder, f"{self.settings.theme}.scss"
            )

        dm_css = os.path.join(static_folder, "css", "vendors", "bootstrap.min.css")
        css = sass.compile(
            filename=theme_scss_file,
            output_style="compressed",
        )
        with open(dm_css, "w") as css_file:
            css_file.write(css)

    def change_theme(self, theme_name):
        self.settings.theme = theme_name
        self.compile_theme()

    @staticmethod
    def load_shared_cards():
        """
        Loads the shared_cards.toml file, to give access to all of the Dashboard objects
        in self.dashboards. shared_cards.toml is configured the same way as any
        dashboard toml file.

        :return shared_cards: (list<dict>) list of card configuration key/value pairs
        """
        try:
            shared_cards = toml.load(shared_cards_toml)
        except Exception as e:
            logging.error("Could not load shard cards.", exc_info=True)
            return {}
        logging.info("Shared cards loaded")
        return shared_cards

    @staticmethod
    def get_logs():
        """
        Returns the contents of the log file as text/html.

        :return logs: (string/html) contents of the log file
        """
        logs_path = os.path.join(root_folder, "dashmachine.log")
        if os.path.isfile(logs_path):
            with open(logs_path, "r") as logs_file:
                lines = logs_file.readlines()
                lines.reverse()
                return Markup("<br>".join(lines))
        else:
            return "Logs were deleted?"
