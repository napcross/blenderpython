#
# This source file is part of appleseed.
# Visit http://appleseedhq.net/ for additional information and resources.
#
# This software is released under the MIT license.
#
# Copyright (c) 2013 Franz Beaune, Joel Daniels, Esteban Tovagliari.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

bl_info = {
    "name": "Appleseed",
    "author": "Franz Beaune, Joel Daniels, Esteban Tovagliari",
    "version": (0, 2, 1),
    "blender": (2, 6, 7),
    "location": "Info Header (engine dropdown)",
    "description": "Appleseed integration",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Render"}

if "bpy" in locals():
    import imp
    imp.reload( properties)
    imp.reload( nodes)
    imp.reload( operators)
    imp.reload( export)
    imp.reload( ui)
    imp.reload( render)
    imp.reload( util)
    imp.reload( preferences)
else:
    import bpy
    from . import properties
    from . import operators
    from . import export
    from . import ui
    from . import render
    from . import util
    from . import preferences

import bpy, bl_ui, bl_operators
import math, mathutils
from shutil import copyfile
from datetime import datetime
import os, subprocess, time

def square( x):
    return x * x

def rad_to_deg( rad):
    return rad * 180.0 / math.pi

def is_black( color):
    return color[0] == 0.0 and color[1] == 0.0 and color[2] == 0.0

def add( color1, color2):
    return [ color1[0] + color2[0], color1[1] + color2[1], color1[2] + color2[2] ]

def mul( color, multiplier):
    return [ color[0] * multiplier, color[1] * multiplier, color[2] * multiplier ]

def scene_enumerator( self, context):
    matches = []
    for scene in bpy.data.scenes:
        matches.append(( scene.name, scene.name, ""))
    return matches

def camera_enumerator( self, context):
    return object_enumerator( 'CAMERA')

def object_enumerator( type):
    matches = []
    for object in bpy.data.objects:
        if object.type == type:
            matches.append(( object.name, object.name, ""))
    return matches
                
def is_uv_img( tex):
    if tex and tex.type == 'IMAGE' and tex.image:
        return True

    return False

#--------------------------------------------------------------------------------------------------
# AppleseedExportOperator class.
#--------------------------------------------------------------------------------------------------

class AppleseedExportOperator( bpy.types.Operator):
    bl_idname = "appleseed.export"
    bl_label = "Export"
    
    textures_set = set()
    
    selected_scene = bpy.props.EnumProperty(name="Scene",
                                            description="Select the scene to export",
                                            items=scene_enumerator)

    selected_camera = bpy.props.EnumProperty(name="Camera",
                                             description="Select the camera to export",
                                             items=camera_enumerator)





    point_lights_exitance_mult = bpy.props.FloatProperty(name="Point Lights Energy Multiplier",
                                                         description="Multiply the exitance of point lights by this factor",
                                                         min=0.0,
                                                         max=1000.0,
                                                         default=1.0,
                                                         subtype='FACTOR')

    spot_lights_exitance_mult = bpy.props.FloatProperty(name="Spot Lights Energy Multiplier",
                                                        description="Multiply the exitance of spot lights by this factor",
                                                        min=0.0,
                                                        max=1000.0,
                                                        default=1.0,
                                                        subtype='FACTOR')

    

    env_exitance_mult = bpy.props.FloatProperty(name="Environment Energy Multiplier",
                                                description="Multiply the exitance of the environment by this factor",
                                                min=0.0,
                                                max=1000.0,
                                                default=1.0,
                                                subtype='FACTOR')

    specular_mult = bpy.props.FloatProperty(name="Specular Components Multiplier",
                                            description="Multiply the intensity of specular components by this factor",
                                            min=0.0,
                                            max=1000.0,
                                            default=1.0,
                                            subtype='FACTOR')


    recompute_vertex_normals = bpy.props.BoolProperty(name="Recompute Vertex Normals",
                                                      description="If checked, vertex normals will be recomputed during tessellation",
                                                      default=True)



    # Transformation matrix applied to all entities of the scene.
    global_scale = 0.1
    global_matrix = mathutils.Matrix.Scale(global_scale, 4)

    def execute( self, context):
        self.textures_set.clear()
        scene = context.scene
        self.export(scene)
        return {'FINISHED'}


    def __get_selected_scene(self):
        if self.selected_scene is not None and self.selected_scene in bpy.data.scenes:
            return bpy.data.scenes[self.selected_scene]
        else: return None

    def __get_selected_camera(self):
        if self.selected_camera is not None and self.selected_camera in bpy.data.objects:
            return bpy.data.objects[self.selected_camera]
        else: return None

    def export(self, scene):
        #scene = self.__get_selected_scene()

        if scene is None:
            self.__error("No scene to export.")
            return

        # Blender material -> front material name, back material name.
        self._emitted_materials = {}

        # Object name -> instance count.
        self._instance_count = {}

        # Object name -> (material index, mesh name).
        self._mesh_parts = {}

        file_path = os.path.splitext( util.realpath(scene.appleseed.project_path) + os.path.sep + scene.name)[0] + ".appleseed"

        self.__info("")
        self.__info("Starting export of scene '{0}' to {1}...".format(scene.name, file_path))

        start_time = datetime.now()

        try:
            with open(file_path, "w") as self._output_file:
                self._indent = 0
                self.__emit_file_header()
                self.__emit_project(scene)
        except IOError:
            self.__error("Could not write to {0}.".format(file_path))
            return

        elapsed_time = datetime.now() - start_time
        self.__info("Finished exporting in {0}".format(elapsed_time))
        

    def __emit_file_header(self):
        self.__emit_line("<?xml version=\"1.0\" encoding=\"UTF-8\"?>")
        self.__emit_line("<!-- File generated by {0} {1}. -->".format( "render_appleseed", "0.1"))

    def __emit_project(self, scene):
        self.__open_element("project")
        self.__emit_scene(scene)
        self.__emit_output(scene)
        self.__emit_configurations(scene)
        self.__close_element("project")

    #----------------------------------------------------------------------------------------------
    # Scene.
    #----------------------------------------------------------------------------------------------

    def __emit_scene(self, scene):
        self.__open_element("scene")
        self.__emit_camera(scene)
        self.__emit_environment(scene)
        self.__emit_assembly(scene)
        self.__emit_assembly_instance_element(scene)
        self.__close_element("scene")

    def __emit_assembly(self, scene):
        self.__open_element('assembly name="' + scene.name + '"')
        self.__emit_physical_surface_shader_element()
        self.__emit_default_material(scene)
        self.__emit_objects(scene)
        self.__close_element("assembly")

    def __emit_assembly_instance_element(self, scene):
        self.__open_element('assembly_instance name="' + scene.name + '_instance" assembly="' + scene.name + '"')
        self.__close_element("assembly_instance")

    def __emit_objects(self, scene):
        inscenelayer = lambda o:scene.layers[next((i for i in range(len(o.layers)) if o.layers[i]))]
        for object in scene.objects:
            if inscenelayer(object) and not object.hide:            
                # Skip objects marked as non-renderable.
                if object.hide_render:
                    continue
    
                # Skip cameras since they are exported separately.
                if object.type == 'CAMERA':
                    continue
    
                if object.type == 'LAMP':
                    self.__emit_light(scene, object)
                else:
                    self.__emit_geometric_object(scene, object)

    #----------------------------------------------------------------------------------------------
    # Camera.
    #----------------------------------------------------------------------------------------------

    def __emit_camera(self, scene):
        camera = self.__get_selected_camera()

        if camera is None:
            self.__warning("No camera in the scene, exporting a default camera.")
            self.__emit_default_camera_element()
            return

        render = scene.render

        film_width = camera.data.sensor_width / 1000
        aspect_ratio = self.__get_frame_aspect_ratio(render)
        lens_unit = "focal_length" if camera.data.lens_unit == 'MILLIMETERS' else "horizontal_fov"
        focal_length = camera.data.lens / 1000.0                # Blender's camera focal length is expressed in mm
        fov = math.degrees(camera.data.angle)
        

        camera_matrix = self.global_matrix * camera.matrix_world
        origin = camera_matrix.col[3]
        forward = -camera_matrix.col[2]
        up = camera_matrix.col[1]
        target = origin + forward
        
        if camera.data.dof_object is not None:
            cam_target = bpy.data.objects[camera.data.dof_object.name]
            focal_distance = (cam_target.location - camera.location).magnitude * 0.1
        else:
            focal_distance = camera.data.dof_distance * 0.1
        
        cam_model = scene.appleseed.camera_type
        self.__open_element('camera name="' + camera.name + '" model="{}_camera"'.format(cam_model))
        if cam_model == "thinlens":
            self.__emit_parameter("f_stop", scene.appleseed.camera_dof)
            self.__emit_parameter("focal_distance", focal_distance)
        self.__emit_parameter("film_width", film_width)
        self.__emit_parameter("aspect_ratio", aspect_ratio)
        self.__emit_parameter(lens_unit, focal_length if camera.data.lens_unit == 'MILLIMETERS' else fov)
        self.__open_element("transform")
        self.__emit_line('<look_at origin="{0} {1} {2}" target="{3} {4} {5}" up="{6} {7} {8}" />'.format( \
                         origin[0], origin[2], -origin[1],
                         target[0], target[2], -target[1],
                         up[0], up[2], -up[1]))
        self.__close_element("transform")
        self.__close_element("camera")

    def __emit_default_camera_element(self):
        self.__open_element('camera name="camera" model="pinhole_camera"')
        self.__emit_parameter("film_width", 0.024892)
        self.__emit_parameter("film_height", 0.018669)
        self.__emit_parameter("focal_length", 0.035)
        self.__close_element("camera")
        return

    #----------------------------------------------------------------------------------------------
    # Environment.
    #----------------------------------------------------------------------------------------------

    def __emit_environment(self, scene):    
        horizon_exitance = [ 0.0, 0.0, 0.0 ]
        zenith_exitance = [ 0.0, 0.0, 0.0 ]

        # Add the contribution of the first hemi light found in the scene.
        found_hemi_light = False
        for object in scene.objects:
            if object.hide_render:
                continue
            if object.type == 'LAMP' and object.data.type == 'HEMI':
                if not found_hemi_light:
                    self.__info("Using hemi light '{0}' for environment lighting.".format(object.name))
                    hemi_exitance = mul(object.data.color, object.data.energy)
                    horizon_exitance = add(horizon_exitance, hemi_exitance)
                    zenith_exitance = add(zenith_exitance, hemi_exitance)
                    found_hemi_light = True
                else:
                    self.__warning("Ignoring hemi light '{0}', multiple hemi lights are not supported yet.".format(object.name))

        # Add the contribution of the sky.
        if scene.world is not None:
            horizon_exitance = add(horizon_exitance, scene.world.horizon_color)
            zenith_exitance = add(zenith_exitance, scene.world.zenith_color)

        # Emit the environment EDF and environment shader if necessary.
        if is_black(horizon_exitance) and is_black(zenith_exitance) and not scene.appleseed_sky.env_type == "sunsky":
            env_edf_name = ""
            env_shader_name = ""
        else:
            # Emit the exitances.
            self.__emit_solid_linear_rgb_color_element("horizon_exitance", horizon_exitance, self.env_exitance_mult)
            self.__emit_solid_linear_rgb_color_element("zenith_exitance", zenith_exitance, self.env_exitance_mult)

            # Emit the environment EDF.
            env_edf_name = "environment_edf"
            if scene.appleseed_sky.env_type == "gradient":
                self.__open_element('environment_edf name="{0}" model="gradient_environment_edf"'.format(env_edf_name))
                self.__emit_parameter("horizon_exitance", "horizon_exitance")
                self.__emit_parameter("zenith_exitance", "zenith_exitance")
                self.__close_element('environment_edf')
                
            elif scene.appleseed_sky.env_type == "constant":
                self.__open_element('environment_edf name="{0}" model="constant_environment_edf"'.format(env_edf_name))
                self.__emit_parameter("radiance", "horizon_exitance")
                self.__close_element('environment_edf')
                
            elif scene.appleseed_sky.env_type == "constant_hemisphere":
                self.__open_element('environment_edf name="{0}" model="constant_hemisphere_environment_edf"'.format(env_edf_name))
                self.__emit_parameter("lower_hemi_radiance", "horizon_exitance")
                self.__emit_parameter("upper_hemi_radiance", "zenith_exitance")
                self.__close_element('environment_edf')
                
            elif scene.appleseed_sky.env_type == "mirrorball_map":
                if scene.appleseed_sky.env_tex != "":
                    self.__emit_texture(bpy.data.textures[scene.appleseed_sky.env_tex], False, scene)
                    self.__open_element('environment_edf name="{0}" model="mirrorball_map_environment_edf"'.format(env_edf_name))
                    self.__emit_parameter("radiance", scene.appleseed_sky.env_tex + "_inst")
                    self.__emit_parameter("radiance_multiplier", scene.appleseed_sky.env_tex_mult)
                    self.__close_element('environment_edf')
                else:
                    self.__warning("Mirror Ball environment texture is enabled, but no texture is assigned. Using gradient environment.")
                    self.__open_element('environment_edf name="{0}" model="gradient_environment_edf"'.format(env_edf_name))
                    self.__emit_parameter("horizon_exitance", "horizon_exitance")
                    self.__emit_parameter("zenith_exitance", "zenith_exitance")
                    self.__close_element('environment_edf')
                    
            elif scene.appleseed_sky.env_type == "latlong_map":
                if scene.appleseed_sky.env_tex != "":
                    self.__emit_texture(bpy.data.textures[scene.appleseed_sky.env_tex], False, scene)
                    self.__open_element('environment_edf name="{0}" model="latlong_map_environment_edf"'.format(env_edf_name))
                    self.__emit_parameter("radiance", scene.appleseed_sky.env_tex + "_inst")
                    self.__emit_parameter("radiance_multiplier", scene.appleseed_sky.env_tex_mult)
                    self.__close_element('environment_edf')
                else:
                    self.__warning("Latitude-Longitude environment texture is enabled, but no texture is assigned. Using gradient environment.")
                    self.__open_element('environment_edf name="{0}" model="gradient_environment_edf"'.format(env_edf_name))
                    self.__emit_parameter("horizon_exitance", "horizon_exitance")
                    self.__emit_parameter("zenith_exitance", "zenith_exitance")
                    self.__close_element('environment_edf')
                    
            elif scene.appleseed_sky.env_type == "sunsky":
                asr_sky = scene.appleseed_sky
                self.__open_element('environment_edf name="{0}" model="{1}"'.format(env_edf_name, asr_sky.sun_model))
                if asr_sky.sun_model == "hosek_environment_edf":
                    self.__emit_parameter("ground_albedo", asr_sky.ground_albedo)
                self.__emit_parameter("horizon_shift", asr_sky.horiz_shift)
                self.__emit_parameter("luminance_multiplier", asr_sky.luminance_multiplier)
                self.__emit_parameter("saturation_multiplier", asr_sky.saturation_multiplier)
                self.__emit_parameter("sun_phi", asr_sky.sun_phi)
                self.__emit_parameter("sun_theta", asr_sky.sun_theta)
                self.__emit_parameter("turbidity", asr_sky.turbidity)
                self.__emit_parameter("turbidity_max", asr_sky.turbidity_max)
                self.__emit_parameter("turbidity_min", asr_sky.turbidity_min)
                self.__close_element('environment_edf')

            # Emit the environment shader.
            env_shader_name = "environment_shader"
            self.__open_element('environment_shader name="{0}" model="edf_environment_shader"'.format(env_shader_name))
            self.__emit_parameter("environment_edf", env_edf_name)
            self.__close_element('environment_shader')

        # Emit the environment element.
        self.__open_element('environment name="environment" model="generic_environment"')
        if len(env_edf_name) > 0:
            self.__emit_parameter("environment_edf", env_edf_name)
        if len(env_shader_name) > 0:
            self.__emit_parameter("environment_shader", env_shader_name)
        self.__close_element('environment')

    #----------------------------------------------------------------------------------------------
    # Geometry.
    #----------------------------------------------------------------------------------------------

    def __emit_geometric_object(self, scene, object):
        # Skip children of dupli objects.
        if object.parent and object.parent.dupli_type in { 'VERTS', 'FACES' }:      # todo: what about dupli type 'GROUP'?
            return

        if object.dupli_type != 'NONE':
            object.dupli_list_create(scene)
            dupli_objects = [ (dupli.object, dupli.matrix) for dupli in object.dupli_list ]
        else:
            dupli_objects = [ (object, object.matrix_world) ]

        # Emit the dupli objects.
        for dupli_object in dupli_objects:
            self.__emit_dupli_object(scene, dupli_object[0], dupli_object[1])

        # Clear dupli list.
        if object.dupli_type != 'NONE':
            object.dupli_list_clear()

    def __emit_dupli_object(self, scene, object, object_matrix):
        # Emit the object the first time it is encountered.
        if object.name in self._instance_count:
            pass
        else:
            try:
                # Tessellate the object.
                mesh = object.to_mesh(scene, True,'RENDER')

                if hasattr(mesh, 'polygons'):
                    # Blender 2.63 and newer: handle BMesh.
                    mesh.calc_tessface()
                    mesh_faces = mesh.tessfaces
                    mesh_uvtex = mesh.tessface_uv_textures
                else:
                    # Blender 2.62 and older.
                    mesh_faces = mesh.faces
                    mesh_uvtex = mesh.uv_textures
 
                # Write the geometry to disk and emit a mesh object element.
                self._mesh_parts[object.name] = self.__emit_mesh_object(scene, object, mesh, mesh_faces, mesh_uvtex)

                # Delete the tessellation.
                bpy.data.meshes.remove(mesh)
            except RuntimeError:
                self.__info("Skipping object '{0}' of type '{1}' because it could not be converted to a mesh.".format(object.name, object.type))
                return

        # Emit the object instance.
        self.__emit_mesh_object_instance(object, object_matrix, scene)

    def __emit_mesh_object(self, scene, object, mesh, mesh_faces, mesh_uvtex):
        if len(mesh_faces) == 0:
            self.__info("Skipping object '{0}' since it has no faces once converted to a mesh.".format(object.name))
            return []

        mesh_filename = object.name + ".obj"

        if scene.appleseed.generate_mesh_files:
            # Recalculate vertex normals.
            if self.recompute_vertex_normals:
                mesh.calc_normals()

            # Export the mesh to disk.
            self.__progress("Exporting object '{0}' to {1}...".format( object.name, mesh_filename))
            mesh_filepath = os.path.join(os.path.dirname( util.realpath( scene.appleseed.project_path) + os.path.sep  + scene.name), mesh_filename)
            try:
                mesh_parts = util.write_mesh_to_disk( mesh, mesh_faces, mesh_uvtex, mesh_filepath)
            except IOError:
                self.__error("While exporting object '{0}': could not write to {1}, skipping this object.".format(object.name, mesh_filepath))
                return []
        else:
            # Build a list of mesh parts just as if we had exported the mesh to disk.
            material_indices = set()
            for face in mesh_faces:
                material_indices.add(face.material_index)
            mesh_parts = map(lambda material_index : (material_index, "part_%d" % material_index), material_indices)

        # Emit object.
        self.__emit_object_element(object.name, mesh_filename, object)

        return mesh_parts

    def __emit_mesh_object_instance(self, object, object_matrix, scene):
        # Emit BSDFs and materials if they are encountered for the first time.
        for material_slot_index, material_slot in enumerate(object.material_slots):
            material = material_slot.material
            if material is None:
                self.__warning("While exporting instance of object '{0}': material slot #{1} has no material.".format(object.name, material_slot_index))
                continue
            if material not in self._emitted_materials:
                self._emitted_materials[material] = self.__emit_material(material, scene)

        # Figure out the instance number of this object.
        if object.name in self._instance_count:
            instance_index = self._instance_count[object.name] + 1
        else:
            instance_index = 0
        self._instance_count[object.name] = instance_index

        # Emit object parts instances.
        for (material_index, mesh_name) in self._mesh_parts[object.name]:
            part_name = "{0}.{1}".format(object.name, mesh_name)
            instance_name = "{0}.instance_{1}".format(part_name, instance_index)
            front_material_name = "__default_material"
            back_material_name = "__default_material"
            if material_index < len(object.material_slots):
                material = object.material_slots[material_index].material
                if material:
                    front_material_name, back_material_name = self._emitted_materials[material]
            self.__emit_object_instance_element(part_name, instance_name, self.global_matrix * object_matrix, front_material_name, back_material_name, object)

    def __emit_object_element(self, object_name, mesh_filepath, object):
        self.__open_element('object name="' + object_name + '" model="mesh_object"')
        self.__emit_parameter("filename", mesh_filepath)
        self.__close_element("object")

    def __emit_object_instance_element(self, object_name, instance_name, instance_matrix, front_material_name, back_material_name, object):
        self.__open_element('object_instance name="{0}" object="{1}"'.format(instance_name, object_name))
        self.__emit_transform_element(instance_matrix)
        self.__emit_line('<assign_material slot="0" side="front" material="{0}" />'.format(front_material_name))
        self.__emit_line('<assign_material slot="0" side="back" material="{0}" />'.format(back_material_name))
        if bool(object.appleseed_render_layer):
            render_layer = object.appleseed_render_layer
            self.__emit_parameter("render_layer", render_layer)
        self.__close_element("object_instance")

    #----------------------------------------------------------------------------------------------
    # Materials.
    #----------------------------------------------------------------------------------------------

    def __is_light_emitting_material(self, material, scene):
        #if material.get('appleseed_arealight', False):
        #return True;
        asr_mat = material.appleseed
        
        return asr_mat.use_light_emission and scene.appleseed.export_emitting_obj_as_lights

    def __emit_physical_surface_shader_element(self):
        self.__emit_line('<surface_shader name="physical_surface_shader" model="physical_surface_shader" />')

    def __emit_default_material(self, scene):
        self.__emit_solid_linear_rgb_color_element("__default_material_bsdf_reflectance", [ 0.8 ], 1.0)

        self.__open_element('bsdf name="__default_material_bsdf" model="lambertian_brdf"')
        self.__emit_parameter("reflectance", "__default_material_bsdf_reflectance")
        self.__close_element("bsdf")

        self.__emit_material_element("__default_material", "__default_material_bsdf", "", "physical_surface_shader", scene, "")

    def __emit_material(self, material, scene):
        asr_mat = material.appleseed
        layers = asr_mat.layers
        front_material_name = ""
                    
        #Need to iterate through layers only once, to find out if we have any specular btdfs
        for layer in layers:
            if layer.bsdf_type == "specular_btdf":
                front_material_name = material.name + "_front"
                back_material_name = material.name + "_back"
                self.__emit_front_material(material, front_material_name, scene, layers)
                self.__emit_back_material(material, back_material_name, scene, layers)
                break
        
        #If we didn't find any, then we're only exporting front material     #DEBUG
        if front_material_name == "":
            front_material_name = material.name
            self.__emit_front_material(material, front_material_name, scene, layers)
            if self.__is_light_emitting_material(material, scene):
                # Assign the default material to the back face if the front face emits light,
                # as we don't want mesh lights to emit from both faces.
                back_material_name = "__default_material"
            else: back_material_name = front_material_name

        return front_material_name, back_material_name

    def __emit_front_material(self, material, material_name, scene, layers):
        #material_name here is material.name + "_front" #DEBUG
        bsdf_name = self.__emit_front_material_bsdf_tree(material, material_name, scene, layers)

        if self.__is_light_emitting_material(material, scene):
            edf_name = "{0}_edf".format(material_name)
            self.__emit_edf(material, edf_name, scene)
        else: edf_name = ""

        self.__emit_material_element(material_name, bsdf_name, edf_name, "physical_surface_shader", scene, material)

    def __emit_back_material(self, material, material_name, scene, layers):
        #material_name here is material.name + "_back" #DEBUG
        bsdf_name = self.__emit_back_material_bsdf_tree(material, material_name, scene, layers)
        self.__emit_material_element(material_name, bsdf_name, "", "physical_surface_shader", scene, material)
    
    
    def __emit_front_material_bsdf_tree(self, material, material_name, scene, layers):
        #material_name here is material.name + "_front" #DEBUG
        bsdfs = []
        asr_mat = material.appleseed
        #Iterate through layers and export their types, append names and weights to bsdfs list
        if len(layers) == 0:
            default_bsdf_name = "__default_material_bsdf"
            return default_bsdf_name
        else:
            for layer in layers:
                if layer.bsdf_type == "specular_btdf":
                    transp_bsdf_name = "{0}|{1}".format(material_name, layer.name)
                    self.__emit_specular_btdf(material, transp_bsdf_name, 'front', layer)
                    bsdfs.append([ transp_bsdf_name, layer.spec_btdf_weight ])
    
                elif layer.bsdf_type == "specular_brdf":
                    mirror_bsdf_name = "{0}|{1}".format(material_name, layer.name)
                    self.__emit_specular_brdf(material, mirror_bsdf_name, scene, layer)
                    bsdfs.append([ mirror_bsdf_name, layer.specular_weight ])
    
                elif layer.bsdf_type == "diffuse_btdf":   
                    dt_bsdf_name = "{0}|{1}".format(material_name, layer.name)
                    self.__emit_diffuse_btdf(material, dt_bsdf_name, scene, layer)
                    bsdfs.append([ dt_bsdf_name, layer.transmission_weight])
            
                elif layer.bsdf_type == "lambertian_brdf":
                    lbrt_bsdf_name = "{0}|{1}".format(material_name, layer.name)
                    self.__emit_lambertian_brdf(material, lbrt_bsdf_name, scene, layer)
                    bsdfs.append([ lbrt_bsdf_name, layer.lambertian_weight])
                
                elif layer.bsdf_type == "ashikhmin_brdf":
                    ashk_bsdf_name = "{0}|{1}".format(material_name, layer.name)
                    self.__emit_ashikhmin_brdf(material, ashk_bsdf_name, scene, layer)
                    bsdfs.append([ ashk_bsdf_name, layer.ashikhmin_weight ])
                    
                elif layer.bsdf_type == "microfacet_brdf":
                    mfacet_bsdf_name = "{0}|{1}".format(material_name, layer.name)
                    self.__emit_microfacet_brdf(material, mfacet_bsdf_name, scene, layer)
                    bsdfs.append([ mfacet_bsdf_name, layer.microfacet_weight])
                    
                elif layer.bsdf_type == "kelemen_brdf":
                    kelemen_bsdf_name = "{0}|{1}".format(material_name, layer.name)
                    self.__emit_kelemen_brdf(material, kelemen_bsdf_name, scene, layer)
                    bsdfs.append([ kelemen_bsdf_name, layer.kelemen_weight])
                  
            return self.__emit_bsdf_blend(bsdfs)
    
    #------------------------------------------------------------------------
    
    def __emit_back_material_bsdf_tree(self, material, material_name, scene, layers):
        #material_name = material.name  + "_back"
        #Need to include all instances of spec btdfs - iterate -> layers, find them, add to list
        spec_btdfs = []
        for layer in layers:
            if layer.bsdf_type == "specular_btdf":
                #This is a hack for now; just return the first one we find
                spec_btdfs.append([layer.name, layer.spec_btdf_weight])
                transp_bsdf_name = "{0}|{1}".format(material_name, spec_btdfs[0][0]) 
                
                self.__emit_specular_btdf(material, transp_bsdf_name, 'back', layer)
        

        
        return transp_bsdf_name
    
    #------------------------------------
    
    def __emit_bsdf_blend(self, bsdfs):
        
        # Only one BSDF, no blending.
        if len(bsdfs) == 1:
            return bsdfs[0][0]

        # Normalize weights if necessary.
        total_weight = 0.0
        for bsdf in bsdfs:
            total_weight += bsdf[1]
        if total_weight > 1.0:
            for bsdf in bsdfs:
                bsdf[1] /= total_weight

        # The left branch is simply the first BSDF.
        bsdf0_name = bsdfs[0][0]
        bsdf0_weight = bsdfs[0][1]

        # The right branch is a blend of all the other BSDFs (recurse).
        bsdf1_name = self.__emit_bsdf_blend(bsdfs[1:])
        bsdf1_weight = 1.0 - bsdf0_weight

        # Blend the left and right branches together.
        mix_name = "{0}+{1}".format(bsdf0_name, bsdf1_name)
        self.__emit_bsdf_mix(mix_name, bsdf0_name, bsdf0_weight, bsdf1_name, bsdf1_weight)
            
        return mix_name
    
    #------------------------------------------------------------
    
    def __emit_lambertian_brdf(self, material, bsdf_name, scene, layer):
        asr_mat = material.appleseed
        
        reflectance_name = ""
        diffuse_list = []
                    
        if layer.lambertian_use_tex and layer.lambertian_diffuse_tex != '':
            if is_uv_img(bpy.data.textures[layer.lambertian_diffuse_tex]):
                reflectance_name = layer.lambertian_diffuse_tex + "_inst"
                if reflectance_name not in self.textures_set:
                    self.__emit_texture(bpy.data.textures[layer.lambertian_diffuse_tex], False, scene)
                    self.textures_set.add(reflectance_name)

                    
        if reflectance_name == "":            
            reflectance_name = "{0}_lambertian_reflectance".format(bsdf_name)
            self.__emit_solid_linear_rgb_color_element(reflectance_name,
                                                   layer.lambertian_reflectance,
                                                   layer.lambertian_multiplier)

        self.__open_element('bsdf name="{0}" model="lambertian_brdf"'.format(bsdf_name))
        self.__emit_parameter("reflectance", reflectance_name)
        self.__close_element("bsdf")
    #----------------------------------------------------------
    def __emit_diffuse_btdf(self, material, bsdf_name, scene, layer):      
        asr_mat = material.appleseed  
        
        transmittance_name = ""
        
        if layer.transmission_use_tex and layer.transmission_tex != "":
            if is_uv_img(bpy.data.textures[layer.transmission_tex]):    
                transmittance_name = layer.transmission_tex + "_inst"
                if transmittance_name not in self.textures_set:
                    self.textures_set.add(transmittance_name)
                    self.__emit_texture(bpy.data.textures[layer.transmission_tex], False, scene)
    
        if transmittance_name == "":
            transmittance_name = "{0}_diffuse_transmittance".format(bsdf_name)
            self.__emit_solid_linear_rgb_color_element(transmittance_name, 
                                                    layer.transmission_color,
                                                    layer.transmission_multiplier)
                                                    
        self.__open_element('bsdf name="{0}" model="diffuse_btdf"'.format(bsdf_name))
        self.__emit_parameter("transmittance", transmittance_name)
        self.__emit_parameter("transmittance_multiplier", layer.transmission_multiplier)
        self.__close_element("bsdf")
        
    #----------------------------------------------------------
    def __emit_ashikhmin_brdf(self, material, bsdf_name, scene, layer):
        asr_mat = material.appleseed
                
        diffuse_reflectance_name = ""
        glossy_reflectance_name = ""
        
        if layer.ashikhmin_use_diff_tex and layer.ashikhmin_diffuse_tex != "":
            if is_uv_img(bpy.data.textures[layer.ashikhmin_diffuse_tex]):    
                diffuse_reflectance_name = layer.ashikhmin_diffuse_tex + "_inst"
                if diffuse_reflectance_name not in self.textures_set:
                    self.textures_set.add(diffuse_reflectance_name)
                    self.__emit_texture(bpy.data.textures[layer.ashikhmin_diffuse_tex], False, scene)
                
        if layer.ashikhmin_use_gloss_tex and layer.ashikhmin_gloss_tex != "":
            if is_uv_img(bpy.data.textures[layer.ashikhmin_gloss_tex]):    
                glossy_reflectance_name = layer.ashikhmin_gloss_tex + "_inst"
                if glossy_reflectance_name not in self.textures_set:
                    self.__emit_texture(bpy.data.textures[layer.ashikhmin_gloss_tex], False, scene)
                    self.textures_set.add(glossy_reflectance_name)
            
        #Make sure we found some textures. If not, default to material color.
        if diffuse_reflectance_name == "":
            diffuse_reflectance_name = "{0}_ashikhmin_reflectance".format(bsdf_name)
            self.__emit_solid_linear_rgb_color_element(diffuse_reflectance_name,
                                                   layer.ashikhmin_reflectance,
                                                   layer.ashikhmin_multiplier)
        if glossy_reflectance_name == "":    
            glossy_reflectance_name = "{0}_ashikhmin_glossy_reflectance".format(bsdf_name)
            self.__emit_solid_linear_rgb_color_element(glossy_reflectance_name,
                                                   layer.ashikhmin_glossy,
                                                   layer.ashikhmin_glossy_multiplier)

        self.__open_element('bsdf name="{0}" model="ashikhmin_brdf"'.format(bsdf_name))
        self.__emit_parameter("diffuse_reflectance", diffuse_reflectance_name)
        self.__emit_parameter("glossy_reflectance", glossy_reflectance_name)
        self.__emit_parameter("shininess_u", layer.ashikhmin_shininess_u)
        self.__emit_parameter("shininess_v", layer.ashikhmin_shininess_v)
        self.__close_element("bsdf")
    
    #-----------------------------------------------------
    
    def __emit_specular_brdf(self, material, bsdf_name, scene, layer):
        asr_mat = material.appleseed
        
        reflectance_name = ""
        if layer.specular_use_gloss_tex and layer.specular_gloss_tex != "":
            if is_uv_img(bpy.data.textures[layer.specular_gloss_tex]):    
                reflectance_name = layer.specular_gloss_tex + "_inst"
                if reflectance_name not in self.textures_set:
                    self.textures_set.add(reflectance_name)
                    self.__emit_texture(bpy.data.textures[layer.specular_gloss_tex], False, scene)
        if reflectance_name == "":
            reflectance_name = "{0}_specular_reflectance".format(bsdf_name)
            self.__emit_solid_linear_rgb_color_element(reflectance_name, material.mirror_color, 1.0)

        self.__open_element('bsdf name="{0}" model="specular_brdf"'.format(bsdf_name))
        self.__emit_parameter("reflectance", reflectance_name)
        self.__close_element("bsdf")
    
    #-------------------------------------------------------

    def __emit_specular_btdf(self, material, bsdf_name, side, layer):
        assert side == 'front' or side == 'back'
        
        asr_mat = material.appleseed
        
        reflectance_name = ""
        transmittance_name = ""
        
        if layer.spec_btdf_use_tex and layer.spec_btdf_tex != "":
            if is_uv_img(bpy.data.textures[layer.spec_btdf_tex]):    
                reflectance_name = layer.spec_btdf_tex + "_inst"
                if reflectance_name not in self.textures_set:
                    self.textures_set.add(reflectance_name)
                    self.__emit_texture(bpy.data.textures[layer.spec_btdf_tex], False, scene)
        if reflectance_name == "":        
            reflectance_name = "{0}_transp_reflectance".format(bsdf_name)
            self.__emit_solid_linear_rgb_color_element(reflectance_name, layer.spec_btdf_reflectance, layer.spec_btdf_ref_mult)
        
        if layer.spec_btdf_use_trans_tex and layer.spec_btdf_trans_tex != "":
            if is_uv_img(bpy.data.textures[layer.spec_btdf_trans_tex]):    
                transmittance_name = layer.spec_btdf_trans_tex + "_inst"
                if transmittance_name not in self.textures_set:
                    self.textures_set.add(transmittance_name)
                    self.__emit_texture(bpy.data.textures[layer.spec_btdf_trans_tex], False, scene)
        
        if transmittance_name == "":            
            transmittance_name = "{0}_transp_transmittance".format(bsdf_name)
            self.__emit_solid_linear_rgb_color_element(transmittance_name, layer.spec_btdf_transmittance, layer.spec_btdf_trans_mult)

        if side == 'front':
            from_ior = 1.0
            to_ior = layer.spec_btdf_to_ior
        else:
            from_ior = layer.spec_btdf_from_ior
            to_ior = 1.0

        self.__open_element('bsdf name="{0}" model="specular_btdf"'.format(bsdf_name))
        self.__emit_parameter("reflectance", reflectance_name)
        self.__emit_parameter("transmittance", transmittance_name)
        self.__emit_parameter("from_ior", from_ior)
        self.__emit_parameter("to_ior", to_ior)
        self.__close_element("bsdf")
    
    #-------------------------------------------------------------------
    
    def __emit_microfacet_brdf(self, material, bsdf_name, scene, layer):
        asr_mat = material.appleseed
        reflectance_name = ""
        mdf_refl = ""
        
        if layer.microfacet_use_diff_tex and layer.microfacet_diff_tex != "":
            if is_uv_img(bpy.data.textures[layer.microfacet_diff_tex]):
                reflectance_name = layer.microfacet_diff_tex + "_inst"
                if reflectance_name not in self.textures_set:
                    self.__emit_texture(bpy.data.textures[layer.microfacet_diff_tex], False, scene)
                    self.textures_set.add(reflectance_name)
        
        if reflectance_name == "":
            reflectance_name = "{0}_microfacet_reflectance".format(bsdf_name)
            self.__emit_solid_linear_rgb_color_element(reflectance_name,
                                                   layer.microfacet_reflectance,
                                                   layer.microfacet_multiplier)
        if layer.microfacet_use_spec_tex and layer.microfacet_spec_tex != "":
            if is_uv_img(bpy.data.textures[layer.microfacet_spec_tex]):    
                mdf_refl = layer.microfacet_spec_tex + "_inst"
                if mdf_refl not in self.textures_set:
                    self.__emit_texture(bpy.data.textures[layer.microfacet_spec_tex], False, scene)
                    self.textures_set.add(mdf_refl)
        if mdf_refl == "":
            #This changes to a float, if it's not a texture
            if layer.microfacet_model != 'blinn':
                mdf_refl = layer.microfacet_mdf
            else:
                mdf_refl = layer.microfacet_mdf_blinn
                                   
        self.__open_element('bsdf name="{0}" model="microfacet_brdf"'.format(bsdf_name))
        self.__emit_parameter("fresnel_multiplier", layer.microfacet_fresnel)
        self.__emit_parameter("mdf", layer.microfacet_model)
        self.__emit_parameter("mdf_parameter", mdf_refl)
        self.__emit_parameter("reflectance", reflectance_name)
        self.__emit_parameter("reflectance_multiplier", layer.microfacet_multiplier)
        self.__close_element("bsdf")
               
    #---------------------------------------------------------------------
    
    def __emit_kelemen_brdf(self, material, bsdf_name, scene, layer):
        asr_mat = material.appleseed
        reflectance_name = ""
        spec_refl_name  = ""
        
        if layer.kelemen_use_diff_tex:
            if layer.kelemen_diff_tex != "":
                if is_uv_img(bpy.data.textures[layer.kelemen_diff_tex]):
                    reflectance_name = layer.kelemen_diff_tex + "_inst"
                    if reflectance_name not in self.textures_set:
                        self.textures_set.add(reflectance_name)
                        self.__emit_texture(bpy.data.textures[layer.kelemen_diff_tex], False, scene)
        
        if reflectance_name == "":
            reflectance_name = "{0}_kelemen_reflectance".format(bsdf_name)
            self.__emit_solid_linear_rgb_color_element(reflectance_name,
                                                   layer.kelemen_matte_reflectance,
                                                   layer.kelemen_matte_multiplier)
        if layer.kelemen_use_spec_tex and layer.kelemen_spec_tex != "":
            if is_uv_img(bpy.data.textures[layer.kelemen_spec_tex]):    
                spec_refl_name = layer.kelemen_spec_tex + "_inst"
                if spec_refl_name not in self.textures_set:
                    self.textures_set.add(spec_refl_name)
                    self.__emit_texture(bpy.data.textures[layer.kelemen_spec_tex], False, scene)
        if spec_refl_name == "":
            spec_refl_name = "{0}_kelemen_specular".format(bsdf_name)
            self.__emit_solid_linear_rgb_color_element(spec_refl_name, 
                                                    layer.kelemen_specular_reflectance,
                                                    layer.kelemen_specular_multiplier)
                                                    
        self.__open_element('bsdf name="{0}" model="kelemen_brdf"'.format(bsdf_name))
        self.__emit_parameter("matte_reflectance", reflectance_name)
        self.__emit_parameter("matte_reflectance_multiplier", layer.kelemen_matte_multiplier)
        self.__emit_parameter("roughness", layer.kelemen_roughness)
        self.__emit_parameter("specular_reflectance", spec_refl_name)
        self.__emit_parameter("specular_reflectance_multiplier", layer.kelemen_specular_multiplier)
        self.__close_element("bsdf")
    
    #---------------------------------------------------------------------    
    
    def __emit_bsdf_mix(self, bsdf_name, bsdf0_name, bsdf0_weight, bsdf1_name, bsdf1_weight):
        self.__open_element('bsdf name="{0}" model="bsdf_mix"'.format(bsdf_name))
        self.__emit_parameter("bsdf0", bsdf0_name)
        self.__emit_parameter("weight0", bsdf0_weight)
        self.__emit_parameter("bsdf1", bsdf1_name)
        self.__emit_parameter("weight1", bsdf1_weight)
        self.__close_element("bsdf")
    
    #-----------------------------------------------
    
#
#    def __emit_edf(self, material, edf_name):
#        self.__emit_diffuse_edf(material, edf_name)
    
    #This was called _emit_diffuse_edf
    def __emit_edf(self, material, edf_name, scene):
        asr_mat = material.appleseed
        exitance_name = "{0}_exitance".format(edf_name)
        emit_factor = asr_mat.light_emission if asr_mat.light_emission > 0.0 else 1.0
        self.__emit_solid_linear_rgb_color_element(exitance_name,
                                                   asr_mat.light_color,
                                                   emit_factor * scene.appleseed.light_mats_exitance_mult)
        self.__emit_diffuse_edf_element(edf_name, exitance_name)
    
    #------------------------
    
    def __emit_diffuse_edf_element(self, edf_name, exitance_name):
        self.__open_element('edf name="{0}" model="diffuse_edf"'.format(edf_name))
        self.__emit_parameter("exitance", exitance_name)
        self.__close_element("edf")

    #---------------------------------------------
    #Export textures, if any exist on the material
    def __emit_texture(self, tex, bump_bool, scene):        
            #Check that the image texture does not already exist in the folder
            if tex.image.filepath.split(os.path.sep)[-1] not in os.listdir( util.realpath(scene.appleseed.project_path)):    
                src_path = realpath(tex.image.filepath)
                dest_path = os.path.join( util.realpath(scene.appleseed.project_path), tex.image.filepath.split(os.path.sep)[-1])
                #If not, then copy the image
                copyfile(src_path, dest_path)       
            else:
                pass
            color_space = 'linear_rgb' if tex.image.colorspace_settings.name == 'Linear' else 'srgb'      
            self.__open_element('texture name="{0}" model="disk_texture_2d"'.format(tex.name if bump_bool == False else tex.name + "_bump"))
            self.__emit_parameter("color_space", color_space)
            self.__emit_parameter("filename", tex.image.filepath.split(os.path.sep)[-1])
            self.__close_element("texture")
            #Now create texture instance
            self.__emit_texture_instance(tex, bump_bool)
            
            print('Emitting texture', tex.name)

    def __emit_texture_instance(self, texture, bump_bool):
        texture_name = texture.name if bump_bool == False else texture.name + "_bump"
        
        self.__open_element('texture_instance name="{0}_inst" texture="{1}"'.format(texture_name, texture_name))
        self.__emit_parameter("addressing_mode", "wrap" if texture.extension == "REPEAT" else "clamp")
        self.__emit_parameter("filtering_mode", "bilinear")
        self.__close_element("texture_instance")   
        
        
        
    #----------------------------------------------------------#
    #----------------------------------------------------------#   
    #Create the material                                       #
    #----------------------------------------------------------#
    #----------------------------------------------------------#
    def __emit_material_element(self, material_name, bsdf_name, edf_name, surface_shader_name, scene, material):
        if material != "":
            asr_mat = material.appleseed
        bump_map = ""
        sss_shader = ""
        
        #Make sure we're not evaluating the default material.
        if material != "":
            print("\nWriting material element for material: ", material.name, '\n')
            #Check if we're using an SSS surface shader
            if asr_mat.sss_use_shader:
                sss_shader = "fastsss_{0}".format(material.name)
                self.__emit_sss_shader(sss_shader, material.name, scene)   
                print("\nCreating SSS shader for material: ", material.name, "sss shader", sss_shader, '\n') 
            
            if asr_mat.material_use_bump_tex:
                if asr_mat.material_bump_tex != "":
                    if is_uv_img(bpy.data.textures[asr_mat.material_bump_tex]):
                        bump_map = asr_mat.material_bump_tex + "_bump"
                                
            if bump_map != "":
                if bump_map not in self.textures_set:
                    self.__emit_texture(bpy.data.textures[asr_mat.material_bump_tex], True, scene)
                    self.textures_set.add(bump_map)

        self.__open_element('material name="{0}" model="generic_material"'.format(material_name))
        if len(bsdf_name) > 0:
            self.__emit_parameter("bsdf", bsdf_name)
        if len(edf_name) > 0:
            self.__emit_parameter("edf", edf_name)
            
        if material != "":      #In case we're evaluating "__default_material"
            #If we're using a bump map on the material
            if bump_map != "":                        
                self.__emit_parameter("bump_amplitude", asr_mat.material_bump_amplitude)
                self.__emit_parameter("displacement_map", bump_map + "_inst")
                self.__emit_parameter("displacement_method", "normal" if asr_mat.material_use_normalmap else "bump")
                self.__emit_parameter("normal_map_up", "z")
            
            #If we're using an alpha map    
            if asr_mat.material_use_alpha:
                if asr_mat.material_alpha_map != "":
                    self.__emit_parameter("alpha_map", asr_mat.material_alpha_map + "_inst")
                    if asr_mat.material_alpha_map + "_inst" not in self.textures_set:
                        self.__emit_texture(bpy.data.textures[asr_mat.material_alpha_map], False, scene)
                        self.textures_set.add(asr_mat.material_alpha_map + "_inst")
        else:
            pass
        self.__emit_parameter("surface_shader", sss_shader if sss_shader != "" else surface_shader_name)
        self.__close_element("material")
    
    #-------------------------------------        
    def __emit_sss_shader(self, sss_shader_name, material_name, scene):
        material = bpy.data.materials[material_name]
        asr_mat = material.appleseed
        
        albedo_list = []
        
        #Get color texture, if any exist and we're using an albedo texture
        if asr_mat.sss_albedo_use_tex and not asr_mat.sss_albedo_tex != "":
            if is_uv_img(bpy.data.textures[asr_mat.sss_albedo_tex]):
                albedo_name = asr_mat.sss_albedo_tex + "_inst"
                if albedo_name not in self.textures_set:   
                    self.__emit_texture(bpy.data.textures[albedo_list[0]], scene)
                    self.textures_set.add(albedo_name)
            
            #If no texture was found        
            elif albedo_list == []:
                albedo_name = material_name + "_albedo"
                self.__emit_solid_linear_rgb_color_element(material_name + "_albedo", material.subsurface_scattering.color, 1.0)
        
        #If not using albedo textures        
        else:
            self.__emit_solid_linear_rgb_color_element(material_name + "_albedo", material.subsurface_scattering.color, 1.0)
            albedo_name = material_name + "_albedo"
            
        self.__open_element('surface_shader name="{0}" model="fast_sss_surface_shader"'.format(sss_shader_name))
        self.__emit_parameter("albedo", albedo_name)
        self.__emit_parameter("ambient_sss", asr_mat.sss_ambient)
        self.__emit_parameter("diffuse", asr_mat.sss_diffuse)
        self.__emit_parameter("distortion", asr_mat.sss_distortion)
        self.__emit_parameter("light_samples", asr_mat.sss_light_samples)
        self.__emit_parameter("occlusion_samples", asr_mat.sss_occlusion_samples)
        self.__emit_parameter("power", asr_mat.sss_power)
        self.__emit_parameter("scale", asr_mat.sss_scale)
        self.__emit_parameter("view_dep_sss", asr_mat.sss_view_dep)
        self.__close_element("surface_shader")
        
    #----------------------------------------------------------------------------------------------
    # Lights.
    #----------------------------------------------------------------------------------------------

    def __emit_light(self, scene, object):
        light_type = object.data.type

        if light_type == 'POINT':
            self.__emit_point_light(scene, object)
        elif light_type == 'SPOT':
            self.__emit_spot_light(scene, object)
        elif light_type == 'HEMI':
            # Handle by the environment handling code.
            pass
        elif light_type == 'SUN' and scene.appleseed_sky.env_type == "sunsky":
            self.__emit_sun_light(scene, object)
        elif light_type == 'SUN' and not scene.appleseed_sky.env_type == "sunsky":
            self.__warning("Sun lamp '{0}' exists in the scene, but sun/sky is not enabled".format(object.name))
            self.__emit_sun_light(scene, object)
        else:
            self.__warning("While exporting light '{0}': unsupported light type '{1}', skipping this light.".format(object.name, light_type))

    def __emit_sun_light(self, scene, lamp):
        sunsky = scene.appleseed_sky
        use_sunsky = sunsky.env_type == "sunsky"
        environment_edf = "environment_edf"
        
        self.__open_element('light name="{0}" model="sun_light"'.format(lamp.name))
        if bool(lamp.appleseed_render_layer):
            render_layer = lamp.appleseed_render_layer
            self.__emit_parameter("render_layer", render_layer)
        if use_sunsky:    
            self.__emit_parameter("environment_edf", environment_edf)
        self.__emit_parameter("radiance_multiplier", sunsky.radiance_multiplier if use_sunsky else 0.04)
        self.__emit_parameter("turbidity", 4.0)
        self.__emit_transform_element(self.global_matrix * lamp.matrix_world)
        self.__close_element("light")
        
    def __emit_point_light(self, scene, lamp):
        exitance_name = "{0}_exitance".format(lamp.name)
        self.__emit_solid_linear_rgb_color_element(exitance_name, lamp.data.color, lamp.data.energy * self.point_lights_exitance_mult)

        self.__open_element('light name="{0}" model="point_light"'.format(lamp.name))
        if bool(lamp.appleseed_render_layer):
            render_layer = lamp.appleseed_render_layer
            self.__emit_parameter("render_layer", render_layer)
        self.__emit_parameter("exitance", exitance_name)
        self.__emit_transform_element(self.global_matrix * lamp.matrix_world)
        self.__close_element("light")

    def __emit_spot_light(self, scene, lamp):
        exitance_name = "{0}_exitance".format(lamp.name)
        self.__emit_solid_linear_rgb_color_element(exitance_name, lamp.data.color, lamp.data.energy * self.spot_lights_exitance_mult)

        outer_angle = math.degrees(lamp.data.spot_size)
        inner_angle = (1.0 - lamp.data.spot_blend) * outer_angle

        self.__open_element('light name="{0}" model="spot_light"'.format(lamp.name))
        if bool(lamp.appleseed_render_layer):
            render_layer = lamp.appleseed_render_layer
            self.__emit_parameter("render_layer", render_layer)
        self.__emit_parameter("exitance", exitance_name)
        self.__emit_parameter("inner_angle", inner_angle)
        self.__emit_parameter("outer_angle", outer_angle)
        self.__emit_transform_element(self.global_matrix * lamp.matrix_world)
        self.__close_element("light")

    #----------------------------------------------------------------------------------------------
    # Output.
    #----------------------------------------------------------------------------------------------

    def __emit_output(self, scene):
        self.__open_element("output")
        self.__emit_frame_element(scene)
        self.__close_element("output")

    def __emit_frame_element(self, scene):
        camera = self.__get_selected_camera()
        width, height = self.__get_frame_resolution(scene.render)
        self.__open_element("frame name=\"beauty\"")
        self.__emit_parameter("camera", "camera" if camera is None else camera.name)
        self.__emit_parameter("resolution", "{0} {1}".format(width, height))
        self.__emit_custom_prop(scene, "color_space", "srgb")
        self.__close_element("frame")

    def __get_frame_resolution(self, render):
        scale = render.resolution_percentage / 100.0
        width = int(render.resolution_x * scale)
        height = int(render.resolution_y * scale)
        return width, height

    def __get_frame_aspect_ratio(self, render):
        width, height = self.__get_frame_resolution(render)
        xratio = width * render.pixel_aspect_x
        yratio = height * render.pixel_aspect_y
        return xratio / yratio

    #----------------------------------------------------------------------------------------------
    # Configurations.
    #----------------------------------------------------------------------------------------------

    def __emit_configurations(self, scene):
        self.__open_element("configurations")
        self.__emit_interactive_configuration_element(scene)
        self.__emit_final_configuration_element(scene)
        self.__close_element("configurations")

    def __emit_interactive_configuration_element(self, scene):
        self.__open_element('configuration name="interactive" base="base_interactive"')
        self.__emit_common_configuration_parameters(scene, "interactive")
        self.__close_element("configuration")

    def __emit_final_configuration_element(self, scene):
        self.__open_element('configuration name="final" base="base_final"')
        self.__emit_common_configuration_parameters(scene, "final")
        self.__open_element('parameters name="generic_tile_renderer"')
        self.__emit_parameter("min_samples", scene.appleseed.sampler_min_samples)
        self.__emit_parameter("max_samples", scene.appleseed.sampler_max_samples)
        self.__close_element("parameters")
        self.__close_element("configuration")

    def __emit_common_configuration_parameters(self, scene, type):
        #Interactive: always use drt
        lighting_engine = 'drt' if type == "interactive" else scene.appleseed.lighting_engine
        
        self.__emit_parameter("lighting_engine", lighting_engine)
        self.__emit_parameter("pixel_renderer", scene.appleseed.pixel_sampler)
        self.__emit_parameter("rendering_threads", scene.appleseed.threads)
        self.__open_element('parameters name="adaptive_pixel_renderer"')
        self.__emit_parameter("enable_diagnostics", scene.appleseed.enable_diagnostics)
        self.__emit_parameter("max_samples", scene.appleseed.sampler_max_samples)
        self.__emit_parameter("min_samples", scene.appleseed.sampler_min_samples)
        self.__emit_parameter("quality", scene.appleseed.quality)
        self.__close_element("parameters")

        self.__open_element('parameters name="uniform_pixel_renderer"')
        self.__emit_parameter("decorrelate_pixels", scene.appleseed.decorrelate_pixels)
        self.__emit_parameter("samples", scene.appleseed.sampler_max_samples)
        self.__close_element("parameters")
        
        self.__open_element('parameters name="{0}"'.format(scene.appleseed.lighting_engine))
        self.__emit_parameter("dl_light_samples", scene.appleseed.dl_light_samples)
        self.__emit_parameter("enable_ibl", "true" if scene.appleseed.ibl_enable else "false")
        self.__emit_parameter("ibl_env_samples", scene.appleseed.ibl_env_samples)
        if scene.appleseed.lighting_engine == 'pt':
            self.__emit_parameter("enable_dl", "true" if scene.appleseed.direct_lighting else "false")
            self.__emit_parameter("enable_caustics", "true" if scene.appleseed.caustics_enable else "false")
            self.__emit_parameter("max_path_length", scene.appleseed.max_bounces)
            self.__emit_parameter("next_event_estimation", "true" if scene.appleseed.next_event_est else "false")
        self.__emit_parameter("rr_min_path_length", scene.appleseed.rr_start)
        self.__close_element('parameters')

    #----------------------------------------------------------------------------------------------
    # Common elements.
    #----------------------------------------------------------------------------------------------

    def __emit_color_element(self, name, color_space, values, alpha, multiplier):
        self.__open_element('color name="{0}"'.format(name))
        self.__emit_parameter("color_space", color_space)
        self.__emit_parameter("multiplier", multiplier)
        self.__emit_line("<values>{0}</values>".format(" ".join(map(str, values))))
        if alpha:
            self.__emit_line("<alpha>{0}</alpha>".format(" ".join(map(str, alpha))))
        self.__close_element("color")

    #
    # A note on color spaces:
    #
    # Internally, Blender stores colors as linear RGB values, and the numeric color values
    # we get from color pickers are linear RGB values, although the color swatches and color
    # pickers show gamma corrected colors. This explains why we pretty much exclusively use
    # __emit_solid_linear_rgb_color_element() instead of __emit_solid_srgb_color_element().
    #

    def __emit_solid_linear_rgb_color_element(self, name, values, multiplier):
        self.__emit_color_element(name, "linear_rgb", values, None, multiplier)

    def __emit_solid_srgb_color_element(self, name, values, multiplier):
        self.__emit_color_element(name, "srgb", values, None, multiplier)

    def __emit_transform_element(self, m):
        #
        # We have the following conventions:
        #
        #   Both Blender and appleseed use right-hand coordinate systems.
        #   Both Blender and appleseed use column-major matrices.
        #   Both Blender and appleseed use pre-multiplication.
        #   In Blender, given a matrix m, m[i][j] is the element at the i'th row, j'th column.
        #
        # The only difference between the coordinate systems of Blender and appleseed is the up vector:
        # in Blender, up is Z+; in appleseed, up is Y+. We can go from Blender's coordinate system to
        # appleseed's one by rotating by +90 degrees around the X axis. That means that Blender objects
        # must be rotated by -90 degrees around X before being exported to appleseed.
        #

        self.__open_element("transform")
        self.__open_element("matrix")
        self.__emit_line("{0} {1} {2} {3}".format( m[0][0],  m[0][1],  m[0][2],  m[0][3]))
        self.__emit_line("{0} {1} {2} {3}".format( m[2][0],  m[2][1],  m[2][2],  m[2][3]))
        self.__emit_line("{0} {1} {2} {3}".format(-m[1][0], -m[1][1], -m[1][2], -m[1][3]))
        self.__emit_line("{0} {1} {2} {3}".format( m[3][0],  m[3][1],  m[3][2],  m[3][3]))
        self.__close_element("matrix")
        self.__close_element("transform")

    def __emit_custom_prop(self, object, prop_name, default_value):
        value = self.__get_custom_prop(object, prop_name, default_value)
        self.__emit_parameter(prop_name, value)

    def __get_custom_prop(self, object, prop_name, default_value):
        if prop_name in object:
            return object[prop_name]
        else:
            return default_value

    def __emit_parameter(self, name, value):
        self.__emit_line("<parameter name=\"" + name + "\" value=\"" + str(value) + "\" />")

    #----------------------------------------------------------------------------------------------
    # Utilities.
    #----------------------------------------------------------------------------------------------

    def __open_element(self, name):
        self.__emit_line("<" + name + ">")
        self.__indent()

    def __close_element(self, name):
        self.__unindent()
        self.__emit_line("</" + name + ">")

    def __emit_line(self, line):
        self.__emit_indent()
        self._output_file.write(line + "\n")

    def __indent(self):
        self._indent += 1

    def __unindent(self):
        assert self._indent > 0
        self._indent -= 1

    def __emit_indent(self):
        IndentSize = 4
        self._output_file.write(" " * self._indent * IndentSize)

    def __error(self, message):
        self.__print_message("error", message)
        self.report({ 'ERROR' }, message)

    def __warning(self, message):
        self.__print_message("warning", message)
        self.report({ 'WARNING' }, message)

    def __info(self, message):
        if len(message) > 0:
            self.__print_message("info", message)
        else: print("")
        self.report({ 'INFO' }, message)

    def __progress(self, message):
        self.__print_message("progress", message)

    def __print_message(self, severity, message):
        max_length = 8  # length of the longest severity string
        padding_count = max_length - len(severity)
        padding = " " * padding_count
        print( "{0}{1} : {2}".format(severity, padding, message))

def register():
    properties.register()
    operators.register()
    export.register()
    ui.register()
    preferences.register()
    bpy.utils.register_module( __name__)

def unregister():
    properties.unregister()
    operators.register()
    export.unregister()
    ui.unregister()
    preferences.unregister()
    bpy.utils.unregister_module( __name__)

    del bpy.types.Material.appleseed
