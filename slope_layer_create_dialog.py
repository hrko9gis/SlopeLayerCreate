from PyQt5 import uic
from PyQt5.QtWidgets import QDialog
import os

FORM_CLASS, _ = uic.loadUiType(os.path.join(os.path.dirname(__file__), 'slope_layer_create_dialog_base.ui'))

class SlopeLayerCreateDialog(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super(SlopeLayerCreateDialog, self).__init__(parent)
        self.setupUi(self)
