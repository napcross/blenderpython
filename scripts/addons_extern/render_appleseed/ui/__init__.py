
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

import bpy
import bl_ui
from . import render
from . import render_layers
from . import scene
from . import world
from . import camera
from . import objects
from . import materials

import bl_ui.properties_texture as properties_texture
properties_texture.TEXTURE_PT_preview.COMPAT_ENGINES.add( 'APPLESEED_RENDER')
properties_texture.TEXTURE_PT_image.COMPAT_ENGINES.add( 'APPLESEED_RENDER')
properties_texture.TEXTURE_PT_image_mapping.COMPAT_ENGINES.add('APPLESEED_RENDER')
properties_texture.TEXTURE_PT_mapping.COMPAT_ENGINES.add( 'APPLESEED_RENDER')
properties_texture.TEXTURE_PT_preview.COMPAT_ENGINES.add( 'APPLESEED_RENDER')

for member in dir( properties_texture):
        subclass = getattr( bl_ui.properties_texture, member)
        try:
            subclass.COMPAT_ENGINES.add( 'APPLESEED_RENDER')
        except:
            pass
del properties_texture

import bl_ui.properties_data_lamp as properties_data_lamp
properties_data_lamp.DATA_PT_context_lamp.COMPAT_ENGINES.add( 'APPLESEED_RENDER')
properties_data_lamp.DATA_PT_spot.COMPAT_ENGINES.add( 'APPLESEED_RENDER')
properties_data_lamp.DATA_PT_lamp.COMPAT_ENGINES.add( 'APPLESEED_RENDER')
del properties_data_lamp


# Enable all existing panels for these contexts
import bl_ui.properties_data_mesh as properties_data_mesh
for member in dir( properties_data_mesh):
    subclass = getattr( properties_data_mesh, member)
    try: subclass.COMPAT_ENGINES.add( 'APPLESEED_RENDER')
    except: pass
del properties_data_mesh

import bl_ui.properties_data_mesh as properties_data_mesh
for member in dir( properties_data_mesh):
    subclass = getattr( properties_data_mesh, member)
    try: subclass.COMPAT_ENGINES.add( 'APPLESEED_RENDER')
    except: pass
del properties_data_mesh

import bl_ui.properties_particle as properties_particle
for member in dir( properties_particle):
    if member == 'PARTICLE_PT_render': continue

    subclass = getattr( properties_particle, member)
    try: subclass.COMPAT_ENGINES.add( 'APPLESEED_RENDER')
    except:  pass
del properties_particle

def register():
    render.register()
    render_layers.register()
    scene.register()
    world.register()
    materials.register()
    camera.register()
    objects.register()

def unregister():
    render.unregister()
    render_layers.unregister()
    scene.unregister()
    world.unregister()
    materials.unregister()
    camera.unregister()
    objects.unregister()
