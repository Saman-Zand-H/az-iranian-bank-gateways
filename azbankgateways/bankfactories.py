from __future__ import absolute_import, unicode_literals

from django.core.handlers.wsgi import WSGIRequest

import importlib
import logging

from . import default_settings as settings
from .banks import BaseBank
from .exceptions.exceptions import BankGatewayAutoConnectionFailed
from .models import BankType


class BankFactory:
    def __init__(self):
        logging.debug("Create bank factory")
        self._secret_value_reader = self._import(settings.SETTING_VALUE_READER_CLASS)()

    @staticmethod
    def _import(path):
        package, attr = path.rsplit(".", 1)
        klass = getattr(importlib.import_module(package), attr)
        return klass

    def _import_bank(self, bank_type: BankType, identifier: str):
        """
        helper to import bank aliases from string paths.

        raises an AttributeError if a bank can't be found by it's alias
        """
        bank_class = self._import(self._secret_value_reader.klass(bank_type=bank_type, identifier=identifier))
        logging.debug("Import bank class")

        return bank_class, self._secret_value_reader.read(bank_type=bank_type, identifier=identifier)

    def create(self, request: WSGIRequest, bank_type: BankType = None, identifier: str = "1") -> BaseBank:
        """Build bank class"""
        assert hasattr(request, "build_absolute_uri")
        
        if not bank_type:
            bank_type = self._secret_value_reader.default(identifier)
        logging.debug("Request create bank", extra={"bank_type": bank_type})

        bank_klass, bank_settings = self._import_bank(bank_type, identifier)
        bank = bank_klass(**bank_settings, identifier=identifier)
        bank.set_currency(self._secret_value_reader.currency(identifier))
        bank.set_request(request)

        logging.debug("Create bank")
        return bank

    def auto_create(self, request: WSGIRequest, identifier: str = "1", amount=None) -> BaseBank:
        logging.debug("Request create bank automatically")
        bank_list = self._secret_value_reader.get_bank_priorities(identifier)
        for bank_type in bank_list:
            try:
                bank = self.create(request, bank_type, identifier)
                bank.check_gateway(amount)
                return bank
            except Exception as e:
                logging.debug(str(e))
                logging.debug("Try to connect another bank...")
                continue
        raise BankGatewayAutoConnectionFailed()
