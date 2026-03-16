"""QGIS Plugin initialization file."""

from .bo_projektstart import BoProjektstartPlugin


def classFactory(iface):
    """Load BoProjektstartPlugin class from file bo_projektstart.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    return BoProjektstartPlugin(iface)
