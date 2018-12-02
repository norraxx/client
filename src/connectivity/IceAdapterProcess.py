import os
import subprocess
import sys
from threading import Thread
from time import sleep

import fafpath
from PyQt5.QtNetwork import QTcpServer, QHostAddress
from PyQt5.QtWidgets import QMessageBox
from config import Settings
from decorators import with_logger


class IceAdapterLogger(Thread):
    def __init__(self, ice_adapter_process, logger_):
        super(IceAdapterLogger, self).__init__()
        self.ice_adapter_process = ice_adapter_process
        self._logger = logger_

    def run(self):
        while self.ice_adapter_process and self.ice_adapter_process.poll() is None:
            try:
                stdout_data, stderr_data = self.ice_adapter_process.communicate(timeout=.1)
                for row in str(stdout_data).splitlines():
                    self._logger.info("ICE: " + row)
                for row in str(stderr_data).splitlines():
                    self._logger.info("ICE ERROR: " + row)
            except subprocess.TimeoutExpired:
                pass
            finally:
                sleep(.1)

        self.on_exit(self.ice_adapter_process.poll())

    def on_exit(self, code):
        if code:
            self._logger.error("the ICE crashed")
            QMessageBox.critical(None, "ICE adapter error", "The ICE adapter crashed. Please refaf.")

        self._logger.debug("The ICE adapter closed with exit code 0")


@with_logger
class IceAdapterProcess(object):
    def __init__(self, player_id, player_login):

        # determine free listen port for the RPC server inside the ice adapter process
        s = QTcpServer()
        s.listen(QHostAddress.LocalHost, 0)
        self._rpc_server_port = s.serverPort()
        s.close()

        args = []
        if sys.platform == 'win32':
            exe_path = os.path.join(fafpath.get_libdir(), "ice-adapter", "faf-ice-adapter.exe")
        else:  # Expect it to be in PATH already
            exe_path = "java"
            args = ["-jar", "{}".format(os.path.join(fafpath.get_libdir(), "ice-adapter", "faf-ice-adapter.jar"))]

        args.extend([
            "--id", str(player_id),
            "--login", player_login,
            "--rpc-port", str(self._rpc_server_port),
            "--gpgnet-port", "0",
            "--log-level", "debug",
            "--debug-window",
            "--log-directory", Settings.get('client/logs/path', type=str),
        ])

        if Settings.contains('iceadapter/args'):
            args += Settings.get('iceadapter/args', "", type=str).split(" ")

        # print("running ice adapter with {} {}".format(exe_path, " ".join(args)))
        self._logger.debug("running ice adapter with {} {}".format(exe_path, " ".join(args)))
        self.ice_adapter_process = subprocess.Popen([exe_path, *args], stdout=sys.stdout, stderr=sys.stderr)

        # wait for the first message which usually means the ICE adapter is listening for JSONRPC connections
        if not self.ice_adapter_process.pid:
            self._logger.error("error starting the ice adapter process")
            QMessageBox.critical(None, "ICE adapter error", "The ICE adapter did not start. Please refaf.")

        IceAdapterLogger(self.ice_adapter_process, self._logger).start()

    def rpc_port(self):
        return self._rpc_server_port

    def close(self):
        if self.ice_adapter_process and self.ice_adapter_process.poll() is None:
            self._logger.info("Waiting for ice adapter process shutdown")
            try:
                self.ice_adapter_process.wait(300)
            except subprocess.TimeoutExpired:
                self.ice_adapter_process.terminate()
                try:
                    self.ice_adapter_process.wait(300)
                except subprocess.TimeoutExpired:
                    self._logger.error("Killing ice adapter process")
                    self.ice_adapter_process.kill()
