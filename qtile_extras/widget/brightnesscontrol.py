import os

from libqtile import bar
from libqtile.log_utils import logger
from libqtile.utils import add_signal_receiver
from libqtile.widget import base

ERROR_VALUE = -1


class BrightnessControl(base._Widget):

    orientations = base.ORIENTATION_HORIZONTAL

    defaults = [
        ("font", "sans", "Default font"),
        ("fontsize", None, "Font size"),
        ("font_colour", "ffffff", "Colour of text."),
        ("text_format", "{percentage}%", "Text to display."),
        ("bar_colour", "008888", "Colour of bar displaying brightness level."),
        ("error_colour", "880000", "Colour of bar when displaying an error"),
        ("timeout_interval", 5, "Time before widet is hidden."),
        ("widget_width", 75, "Width of bar when widget displayed"),
        (
            "enable_power_saving",
            False,
            (
                "Automatically set brightness depending on status. "
                "Note: this is not checked when the widget is first started."
            )
        ),
        (
            "brightness_on_mains",
            "100%",
            (
                "Brightness level on mains power (accepts integer value"
                "or percentage as string)"
            )
        ),
        (
            "brightness_on_battery",
            "50%",
            (
                "Brightness level on battery power "
                "(accepts integer value or percentage as string)"
            )
        ),
        (
            "device",
            "/sys/class/backlight/intel_backlight",
            "Path to backlight device"
        ),
        (
            "step",
            "5%",
            "Amount to change brightness (accepts int or percentage as string)"
        ),
        (
            "brightness_path",
            "brightness",
            "Name of file holding brightness value"
        ),
        (
            "max_brightness_path",
            "max_brightness",
            "Name of file holding max brightness value"
        ),
        (
            "min_brightness",
            100,
            "Minimum brightness. Do not set to 0!"
        ),
        (
            "max_brightness",
            None,
            "Set value or leave as None to allow device maximum"
        )

    ]

    def __init__(self, **config):
        base._Widget.__init__(self, bar.CALCULATED, **config)
        self.add_defaults(BrightnessControl.defaults)

        self.add_callbacks(
            {
                "Button4": self.cmd_brightness_up,
                "Button5": self.cmd_brightness_down
            }
        )

        # We'll use a timer to hide the widget after a defined period
        self.update_timer = None

        # Set an initial brightness level
        self.percentage = -1

        self.onbattery = False

        # Hide the widget by default
        self.hidden = True

        if self.enable_power_saving:
            self.setup_power_saving()

        self.bright_path = os.path.join(self.device, self.brightness_path)
        self.min = self.min_brightness

        # Get max brightness levels and limit to lower of system add user value
        if self.max_brightness_path:
            self.max_path = os.path.join(self.device, self.max_brightness_path)
            self.max = self.get_max()

            if self.max_brightness:
                self.max = min(self.max, self.max_brightness)

        else:
            if self.max_brightness:
                self.max = self.max_brightness

            else:
                logger.warning("No maximum brightness defined. "
                               "Setting to default value of 500. "
                               "The script may behave unexpectedly.")
                self.max = 500

        # If we've defined a percentage step, calculate this in relation
        # to max value
        if isinstance(self.step, str):
            if self.step.endswith("%"):
                self.step = self.step[:-1]
            val = int(self.step)
            self.step = int(self.max * val / 100)

        # Get current brightness
        self.current = self.get_current()

        # Track previous value so we know if we need to redraw
        self.old = 0

    def _configure(self, qtile, bar):
        base._Widget._configure(self, qtile, bar)
        # Calculate how much space we need to show text
        self.text_width = self.max_text_width()

    async def _config_async(self):
        subscribe = await add_signal_receiver(
                        self.message,
                        session_bus=False,
                        signal_name="PropertiesChanged",
                        path="/org/freedesktop/UPower",
                        dbus_interface="org.freedesktop.DBus.Properties")

        if not subscribe:
            msg = "Unable to add signal receiver for UPower events."
            logger.warning(msg)

    def message(self, message):
        self.update(*message.body)

    def update(self, interface_name, changed_properties,
               invalidated_properties):
        if "OnBattery" not in changed_properties:
            return

        onbattery = changed_properties["OnBattery"].value

        if onbattery != self.onbattery:
            if onbattery:
                value = self.brightness_on_battery
            else:
                value = self.brightness_on_mains

            if type(value) == int:
                self.set_brightness_value(value)
            elif type(value) == str and value.endswith("%"):
                try:
                    percent = int(value[:-1])
                    self.set_brightness_percent(percent / 100)
                except ValueError:
                    err = "Incorrectly formatted brightness: {}".format(value)
                    logger.error(err)
            else:
                err = "Unrecognised value for brightness: {}".format(value)
                logger.warning(err)

            self.onbattery = onbattery

    def max_text_width(self):

        # Calculate max width of text given defined layout
        width, _ = self.drawer.max_layout_size(
            [self.text_format.format(percentage=100)],
            self.font,
            self.fontsize
        )

        return width

    def status_change(self, percentage):
        # The brightness has changed so we need to show the widget
        self.hidden = False

        # Set the value and update the display
        self.percentage = percentage
        self.bar.draw()

        # Start the timer to hide the widget
        self.set_timer()

    def draw(self):
        # Clear the widget backgrouns
        self.drawer.clear(self.background or self.bar.background)

        # If the value is positive then we've succcessully set the brightness
        if self.percentage >= 0:

            # Set colour and text to show current value
            bar_colour = self.bar_colour
            percentage = int(self.percentage * 100)
            text = self.text_format.format(percentage=percentage)
        else:
            # There's been an error so display accordingly
            bar_colour = self.error_colour
            text = "!"

        # Draw the bar
        self.drawer.set_source_rgb(bar_colour)
        self.drawer.fillrect(
            0,
            0,
            self.length * (abs(self.percentage)),
            self.height,
            1
        )

        # Create a text box
        layout = self.drawer.textlayout(
            text,
            self.font_colour,
            self.font,
            self.fontsize,
            None,
            wrap=False
        )

        # We want to centre this vertically
        y_offset = (self.bar.height - layout.height) / 2

        # Set the layout as wide as the widget so text is centred
        layout.width = self.length

        # Add the text to our drawer
        layout.draw(0, y_offset)

        # Redraw the bar
        self.drawer.draw(
            offsetx=self.offset,
            offsety=self.offsety,
            width=self.length
        )

    def set_timer(self):

        # Cancel old timer
        if self.update_timer:
            self.update_timer.cancel()

        # Set new timer
        self.update_timer = self.timeout_add(self.timeout_interval, self.hide)

    def hide(self):

        # Hide the widget
        self.hidden = True
        self.bar.draw()

    def calculate_length(self):

        # If widget is hidden then width should be xero
        if self.hidden:
            return 0

        # Otherwise widget is the greater of the minimum size needed to
        # display 100% and the user defined max
        else:
            return max(self.text_width, self.widget_width)

    def change_brightness(self, step):

        # Get the current brightness level (we need to read this in case
        # the value has been changed elsewhere)
        self.current = self.get_current()

        # If we can read the value then let's process it
        if self.current and self.max:

            # Calculate the new value
            newval = self.current + step

            self._set_brightness(newval)

        else:
            self._set_brightness(ERROR_VALUE)

    def _set_brightness(self, value):

        if value != ERROR_VALUE:
            # Limit brightness so that min <= value <= max
            newval = max(min(value, self.max), self.min)

            # Do we need to set value and trigger callbacks
            if newval != self.old:

                # Set the new value
                success = self._set_current(newval)

                # If we couldn't set value, send the error value
                percentage = newval / self.max if success else ERROR_VALUE

                self.status_change(percentage)

                # Set the previous value
                self.old = newval
        # We should send callbacks if we couldn't read current or max value
        # e.g. to alert user to failure
        else:
            self.status_change(ERROR_VALUE)

    def _read(self, path):
        "Simple method to read value from given path"

        try:
            with open(path, "r") as b:
                value = int(b.read())
        except PermissionError:
            logger.error("Unable to read {}.".format(path))
            value = False
        except ValueError:
            logger.error("Unexpected value when reading {}.".format(path))
            value = False
        except Exception as e:
            logger.error("Unexpected error when reading {}: {}.".format(path,
                                                                        e))
            value = False

        return value

    def get_max(self):
        "Read the max brightness level for the device"

        maxval = self._read(self.max_path)
        if not maxval:
            logger.warning("Max value was not read. "
                           "Module may behave unexpectedly.")
        return maxval

    def get_current(self):
        "Read the current brightness level for the device"

        current = self._read(self.bright_path)
        if not current:
            logger.warning("Current value was not read. "
                           "Module may behave unexpectedly.")
        return current

    def _set_current(self, newval):
        "Set the brightness level for the device"
        try:
            with open(self.bright_path, "w") as b:
                b.write(str(newval))
                success = True
        except PermissionError:
            logger.error("No write access to {}.".format(self.bright_path))
            success = False
        except Exception as e:
            logger.error("Unexpected error when writing"
                         "brightness value: {}.".format(e))
            success = False

        return success

    def cmd_brightness_up(self):
        "Increase the brightness level"
        self.change_brightness(self.step)

    def cmd_brightness_down(self):
        "Decrease the brightness level"
        self.change_brightness(self.step * -1)

    def set_brightness_value(self, value):
        "Set brightess to set value"
        self._set_brightness(value)

    def set_brightness_percent(self, percent):
        "Set brightness to percentage (0.0-1.0) of max value"
        value = int(self.max * percent)
        self._set_brightness(value)
