# compressor.py
#
# Copyright 2019 Hugo Posnic
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import subprocess
from gi.repository import Gtk, Gio, GObject, GLib
from shutil import copy2
from pathlib import Path

from .resultitem import ResultItem
from .tools import message_dialog, get_file_type, sizeof_fmt


SETTINGS_SCHEMA = 'com.github.huluti.Curtail'


class Compressor():
    _settings = Gio.Settings.new(SETTINGS_SCHEMA)

    def __init__(self, win, filename, new_filename):
        super().__init__()

        self.win = win

        # Filenames
        self.filename = filename
        self.new_filename = new_filename

        self.file_data = Path(self.filename)
        self.new_file_data = Path(self.new_filename)

        self.full_name = self.file_data.name

        self.size = self.file_data.stat().st_size

    def run_command(self, command, result_item):
        compression_timeout = self._settings.get_int('compression-timeout')
        try:
            subprocess.call(command,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,
                                 stdin=subprocess.PIPE,
                                 shell=True,
                                 timeout=compression_timeout)
            self.command_finished(result_item)
        except subprocess.TimeoutExpired:
            message = _("Compression has reached the configured timeout of {} seconds. \
You can change it in Preferences.").format(compression_timeout)
            message_dialog(self.win, _("Timeout expired"), message)
            result_item.running = False
            result_item.error = True
        except Exception as err:
            message_dialog(self.win, _("An error has occured"), str(err))
            result_item.running = False
            result_item.error = True

    def compress_image(self):
        result_item = ResultItem(self.full_name, self.filename,
            self.new_filename, sizeof_fmt(self.size), 0, True, False)
        self.win.results_model.append(result_item)

        GLib.idle_add(self.command_start, result_item)

    def command_start(self, result_item):
        lossy = self._settings.get_boolean('lossy')
        metadata = self._settings.get_boolean('metadata')
        file_attributes = self._settings.get_boolean('file-attributes')

        file_type = get_file_type(self.filename)
        if file_type:
            if file_type == 'png':
                command = self.build_png_command(lossy, metadata, file_attributes)
            elif file_type == 'jpg':
                command = self.build_jpg_command(lossy, metadata, file_attributes)
            elif file_type == 'webp':
                command = self.build_webp_command(lossy, metadata)
            self.run_command(command, result_item)  # compress image

    def command_finished(self, result_item):
        new_size = self.new_file_data.stat().st_size
        result_item.size = result_item.size + ' -> ' + sizeof_fmt(new_size)
        result_item.savings = str(round(100 - (new_size * 100 / self.size), 2)) + '%'
        result_item.running = False

    def build_png_command(self, lossy, metadata, file_attributes):
        pngquant = 'pngquant --quality=0-{} -f "{}" --output "{}"'
        optipng = 'optipng -clobber -o{} "{}" -out "{}"'

        if not metadata:
            pngquant += ' --strip'
            optipng += ' -strip all'

        if file_attributes:
            optipng += ' -preserve'

        png_lossy_level = self._settings.get_int('png-lossy-level')
        png_lossless_level = self._settings.get_int('png-lossless-level')

        if lossy:  # lossy compression
            command = pngquant.format(png_lossy_level, self.filename,
                                      self.new_filename)
            command += ' && '
            command += optipng.format(png_lossless_level, self.new_filename,
                                      self.new_filename)
        else: # lossless compression
            command = optipng.format(png_lossless_level, self.filename,
                                     self.new_filename)
        return command

    def build_jpg_command(self, lossy, metadata, file_attributes):
        do_new_file = self._settings.get_boolean('new-file')
        do_jpg_progressive = self._settings.get_boolean('jpg-progressive')

        if do_new_file:
            jpegoptim = 'jpegoptim --max={} -o -f --stdout "{}" > "{}"'
            jpegoptim2 = 'jpegoptim -o -f --stdout "{}" > "{}"'
        else:
            jpegoptim = 'jpegoptim --max={} -o -f "{}"'
            jpegoptim2 = 'jpegoptim -o -f "{}"'

        if do_jpg_progressive:
            jpegoptim += ' --all-progressive'
            jpegoptim2 += ' --all-progressive'

        if not metadata:
            jpegoptim += ' --strip-all'
            jpegoptim2 += ' --strip-all'

        if file_attributes:
            jpegoptim += ' --preserve --preserve-perms'
            jpegoptim2 += ' --preserve --preserve-perms'

        jpg_lossy_level = self._settings.get_int('jpg-lossy-level')
        if lossy:  # lossy compression
            if do_new_file:
                command = jpegoptim.format(jpg_lossy_level, self.filename,
                                           self.new_filename)
            else:
                command = jpegoptim.format(jpg_lossy_level, self.filename)
        else:  # lossless compression
            if do_new_file:
                command = jpegoptim2.format(self.filename, self.new_filename)
            else:
                command = jpegoptim2.format(self.filename)
        return command

    def build_webp_command(self, lossy, metadata):
        command = "cwebp " + self.filename

        # cwebp doesn't preserve any metadata by default
        if metadata:
            command += " -metadata all"

        if lossy:
            quality = self._settings.get_int('webp-lossy-level')
        else:
            command += " -lossless"
            quality = 100   # maximum cpu power for lossless

        compression_level = self._settings.get_int('webp-lossless-level')

        # multithreaded, (lossless) compression mode, quality, output
        command += " -mt -m {}".format(compression_level)
        command += " -q {}".format(quality)
        command += " -o {}".format(self.new_filename)

        return command

