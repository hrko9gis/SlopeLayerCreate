from qgis.PyQt.QtCore import Qt, QVariant, QCoreApplication
from qgis.PyQt.QtWidgets import QAction, QMessageBox, QMenu, QProgressDialog
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.core import *
from qgis.utils import iface
from .slope_layer_create_dialog import SlopeLayerCreateDialog

import os.path
import processing
from processing.core.Processing import Processing

class SlopeLayerCreate:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.plugin_dir = os.path.dirname(__file__)

    def initGui(self):

        self.action = QAction(QIcon(os.path.join(self.plugin_dir, "img", "SlopeLayer.png")), 'SlopeLayerCreate', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        
        self.menu = QMenu(QCoreApplication.translate(u'SlopeLayerCreate', u'SlopeLayerCreate'))
        self.menu.addActions([self.action])
        self.iface.pluginMenu().addMenu(self.menu)

    def unload(self):
        self.iface.removeToolBarIcon(self.action)
        self.iface.removePluginMenu("&SlopeLayerCreate", self.action)

    def run(self):
        self.dlg = SlopeLayerCreateDialog()
        self.populateLayerCombos()
        self.dlg.runButton.clicked.connect(self.processCreateSlopeLayer)
        self.dlg.show()

    def populateLayerCombos(self):
        self.dlg.lineLayerComboBox.clear()
        self.dlg.demLayerComboBox.clear()
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.LineGeometry:
                self.dlg.lineLayerComboBox.addItem(layer.name(), layer)
            elif isinstance(layer, QgsRasterLayer):
                self.dlg.demLayerComboBox.addItem(layer.name(), layer)

    def processCreateSlopeLayer(self):
        line_layer = self.dlg.lineLayerComboBox.currentData()
        dem_layer = self.dlg.demLayerComboBox.currentData()
        
        if not line_layer:
            QMessageBox.warning(self.dlg, "Invalid Input", "Please select LINE layer.")
            return
        
        if not dem_layer:
            QMessageBox.warning(self.dlg, "Invalid Input", "Please select DEM layer.")
            return
        
        try:
            interval = float(self.dlg.intervalLineEdit.text())
        except ValueError:
            QMessageBox.warning(self.dlg, "Invalid Input", "Please enter a valid interval.")
            return

        dem_layer_path = [dem_layer.source()]

        dem_virtual_raster_path = os.path.join(self.plugin_dir,'vrt','dem_virtual_raster.vrt')
        print(dem_virtual_raster_path)
        
        params = {
            'INPUT': dem_layer_path,
            'OUTPUT': dem_virtual_raster_path,
            'RESOLUTION': 1
        }

        Processing.initialize()
        processing.run("gdal:buildvirtualraster", params)
        
        dem_virtual_raster_layer = QgsRasterLayer(dem_virtual_raster_path, "Virtual Raster")
        
        self.create_slope_layer(line_layer, dem_virtual_raster_layer, interval)

    def sample_points_along_line(self, line_geom, interval):
        distance = 0
        length = line_geom.length()
        points = []
        while distance <= length:
            point = line_geom.interpolate(distance).asPoint()
            points.append(point)
            distance += interval
        if distance > length:
            point = line_geom.interpolate(length).asPoint()
            points.append(point)

        return points

    def get_elevation(self, raster_layer, point, crs_src, crs_dest):
        transform = QgsCoordinateTransform(crs_src, crs_dest, QgsProject.instance())
        point_transformed = transform.transform(point)
        ident = raster_layer.dataProvider().identify(point_transformed, QgsRaster.IdentifyFormatValue)
        if ident.isValid():
            return ident.results().get(1)
        return None

    def create_slope_layer(self, line_layer, dem_layer, interval):
        progress = QProgressDialog("Processing...", "Cancel", 0, 100)
        progress.setWindowModality(Qt.WindowModal)
        progress.setAutoClose(True)
        progress.setMinimumDuration(0)
    
        crs_line = line_layer.crs()
        crs_dem = dem_layer.crs()

        slope_layer = QgsVectorLayer("LineString?crs=" + crs_line.authid(), "SlopeLayer", "memory")
        slope_layer.startEditing()
        
        slope_field_name = "percent"
        
        slope_layer.dataProvider().addAttributes([QgsField("f_no", QVariant.Int), QgsField("l_no", QVariant.Int), QgsField("s_no", QVariant.Int), QgsField(slope_field_name, QVariant.Double)])
        #provider.addAttributes([QgsField("angle_rad", QVariant.Double)])
        #provider.addAttributes([QgsField("angle_deg", QVariant.Double)])
        slope_layer.updateFields()
        
        f_no = 1
        l_no = 1
        feature_count = line_layer.featureCount()
        for feature in line_layer.getFeatures():
            progress.setValue(int(l_no / feature_count * 100))
            
            QCoreApplication.processEvents()
            if progress.wasCanceled():
                break
        
            geom = feature.geometry()
            if geom.type() != QgsWkbTypes.LineGeometry:
                continue
            points = self.sample_points_along_line(geom, interval)
            for i in range(len(points) - 1):
                p1, p2 = points[i], points[i + 1]
                z1 = self.get_elevation(dem_layer, p1, crs_line, crs_dem)
                z2 = self.get_elevation(dem_layer, p2, crs_line, crs_dem)
                print("z1:" + str(z1) + ", z2:" + str(z2))
                if z1 is not None and z2 is not None:
                    xy_diff = QgsGeometry.fromPolylineXY([p1, p2]).length()
                    z_diff = z2 - z1
                    if z_diff < 0:
                        z_diff = z_diff * -1
                    slope = z_diff / xy_diff if xy_diff != 0 else 0
                    slp_per = slope * 100
                    print("xy_diff:" + str(xy_diff) + ", z_diff:" + str(z_diff) + ", slope" + str(slope) + ", slope_per" + str(slp_per))
                    #angle_radian = np.arctan(slope)  # ラジアン単位
                    #angle_degrees = np.degrees(angle_radian)  # 度単位
                    f = QgsFeature()
                    f.setGeometry(QgsGeometry.fromPolylineXY([p1, p2]))
                    
                    attributes = []
                    attributes.append(int(f_no))
                    attributes.append(int(l_no))
                    attributes.append(int(i + 1))
                    attributes.append(float(slp_per))
                    #attributes.append([slp_per, angle_radian, angle_degrees])
                    f.setAttributes(attributes)
                    
                    slope_layer.addFeature(f)
                    
                    f_no = f_no + 1
                    
            l_no = l_no + 1

        slope_layer.updateExtents()
        slope_layer.commitChanges()
        QgsProject.instance().addMapLayer(slope_layer)
        
        classification = QgsClassificationJenks()
        ranges = classification.classes(slope_layer, slope_field_name, 5)
        
        ranges_list = []
        for i, range_ in enumerate(ranges):
            symbol = QgsSymbol.defaultSymbol(slope_layer.geometryType())
            symbol.setColor(QColor.fromHsv(240 - 60 * i, 255, 255))
            label = f"{range_.lowerBound()} - {range_.upperBound()}"
            renderer_range = QgsRendererRange(range_.lowerBound(), range_.upperBound(), symbol, label)
            ranges_list.append(renderer_range)

        renderer = QgsGraduatedSymbolRenderer(slope_field_name, ranges_list)
        renderer.setMode(QgsGraduatedSymbolRenderer.Jenks)

        slope_layer.setRenderer(renderer)
        slope_layer.triggerRepaint()
        
        QMessageBox.information(self.dlg,"Completed","Successfully created line slope layer.", QMessageBox.Yes)
        progress.close()
