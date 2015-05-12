import sys
import copy
import shutil
import os

import bpy
from bpy import (types, props)
import mathutils
from mathutils import Color

from .utils import (
    PDBString, quotedPath, setup, todoAndviewpoints, select,
    wait, surface, launch, getVar)

from .app_bootstrap import retrieve_fi_materials
from .app_storage import *


def atomicMLP(MLPcolor, tID):
    materials = bpy.data.materials
    objects = bpy.data.objects

    if MLPcolor:
        for obj in objects:
            try:
                if ((obj.bb2_pdbID == tID) and (obj.bb2_objectType == "ATOM")):
                    aminoName = PDBString(obj.BBInfo).get("aminoName")
                    name = PDBString(obj.BBInfo).get("name")
                    material_this = retrieve_fi_materials(am_name=aminoName, at_name=name)
                    obj.material_slots[0].material = materials[material_this]

            except Exception as E:
                str9 = print(str(E))
        print("Atomic MLP Color set")
    else:
        # Original color
        for obj in objects:
            try:
                if ((obj.bb2_pdbID == tID) and (obj.bb2_objectType == "ATOM")):
                    # In BBInfo, the Atom name is the last string
                    index = obj.BBInfo.split()[-1]
                    obj.material_slots[0].material = materials[index]

            except Exception as E:
                str10 = print(str(E))

        print("Original Atomic Color set")


# do MLP visualization
def mlp(tID, force):
    global dxCache
    global dxData
    global dimension
    global origin
    global delta

    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_RENDER'

    formula = scene.BBMLPFormula
    spacing = scene.BBMLPGridSpacing
    homePath = scene.bb25_homepath
    opSystem = scene.bb25_opSystem
    pyPath = scene.bb25_pyPath

    print('arrives here!')

    if force:
        setup(setupPDBid=tID)
        # select formula for PyMLP script
        if formula == "0":
            method = "dubost"
        elif formula == "1":
            method = "testa"
        elif formula == "2":
            method = "fauchere"
        elif formula == "3":
            method = "brasseur"
        elif formula == "4":
            method = "buckingham"

        # Launch this in a separate process
        if opSystem == "linux":
            command = "chmod 755 %s" % (quotedPath(homePath + "bin" + os.sep + "pyMLP-1.0" + os.sep + "pyMLP.py"))
            command = quotedPath(command)
            launch(exeName=command)
        elif opSystem == "darwin":
            command = "chmod 755 %s" % (quotedPath(homePath + "bin" + os.sep + "pyMLP-1.0" + os.sep + "pyMLP.py"))
            command = quotedPath(command)
            launch(exeName=command)

        print("Running PyMLP")
        if not pyPath:
            pyPath = "python"
        command = "%s %s -i %s -m %s -s %f -o %s -v" % (quotedPath(pyPath), quotedPath(homePath + "bin" + os.sep + "pyMLP-1.0" + os.sep + "pyMLP.py"), quotedPath(homePath + "tmp" + os.sep + "tmp.pdb"), method, spacing, quotedPath(homePath + "tmp" + os.sep + "tmp.dx"))

        p = launch(exeName=command, async=True)

        print("PyMLP command succeded")
        surface(sPid=tID, optName="mlpSurface")

        wait(p)

        # purge all the old data
        dxCache = {}
        dxData = []         # list[n] of Potential data
        dimension = []      # list[3] of dx grid store.dimension
        origin = []         # list[3] of dx grid store.origin
        delta = []          # list[3] of dx grid store.increment

        print("Loading MLP values into Blender")

        try:
            tmpPathO = homePath + "tmp" + os.sep + "tmp.dx"
            with open(tmpPathO) as dx:
                for line in dx:
                    # skip comments starting with #
                    if line[0] == "#":
                        continue
                    if not dimension:
                        # get the store.dimension and convert to integer
                        dim = line.split()[-3:]
                        dimension = [int(d) for d in dim]
                        size = dimension[0] * dimension[1] * dimension[2]
                        continue

                    if not origin:
                        # get the store.origin
                        org = line.split()[-3:]
                        origin = [float(o) for o in org]
                        continue

                    if not delta:
                        # get the increment delta
                        x = float(line.split()[-3:][0])
                        line = dx.readline()
                        y = float(line.split()[-3:][1])
                        line = dx.readline()
                        z = float(line.split()[-3:][2])
                        delta = [x, y, z]

                        # ignore more garbage lines
                        dx.readline()
                        dx.readline()
                        continue

                    # load as much data as we should, ignoring the rest of the file
                    if (len(dxData) >= size):
                        break

                    # Load the data
                    # Convert dx data from str to float, then save to list
                    [dxData.append(float(coord)) for coord in line.split()]
        except Exception as E:
            print("An error occured in MLP while loading values into Blender; be careful; " + str(E))

    # quick and dirty update starts here
    if dxData:
        ob = bpy.data.objects['mlpSurface']
        ob.name = "SURFACE"
        ob.bb2_pdbID = copy.copy(tID)
        ob.bb2_objectType = "SURFACE"
        ob.select = True
        bpy.context.scene.objects.active = ob

        if not bpy.context.vertex_paint_object:
            bpy.ops.paint.vertex_paint_toggle()
        try:
            bpy.ops.object.editmode_toggle()
            bpy.ops.mesh.remove_doubles(threshold=0.0001, use_unselected=False)
            bpy.ops.object.editmode_toggle()
            bpy.ops.object.shade_smooth()
        except Exception as E:
            print("Error in MLP: remove doubles and shade smooth failed; " + str(E))

        try:
            # these are mere references, no copying is taking place.
            local_vars = dimension, delta, origin, dxData, dxCache, ob

            color_map_collection = ob.data.vertex_colors
            if len(color_map_collection) == 0:
                color_map_collection.new()
            color_map = color_map_collection['Col']
            i = 0
            mesh = ob.data
            for poly in mesh.polygons:
                for idx in poly.loop_indices:
                    # tmp = ((0.21 * color_map.data[i].color[0]) + (0.71 * color_map.data[i].color[1]) + (0.07 * color_map.data[i].color[2]))
                    # tmp = (color_map.data[i].color[0] + color_map.data[i].color[1] + color_map.data[i].color[2]) / 3
                    loop = mesh.loops[idx]
                    rawID = loop.vertex_index
                    val = getVar(rawID, local_vars)
                    color_map.data[i].color = val
                    i += 1

        except Exception as E:
            print("Error new color map collection; " + str(E))

        try:
            me = ob.data
        except Exception as E:
            print("Error in MLP: me = ob.data failed; " + str(E))

        try:
            bpy.ops.paint.vertex_paint_toggle()
            me.use_paint_mask = False
            bpy.ops.paint.vertex_color_smooth()
            bpy.ops.paint.vertex_paint_toggle()
        except Exception as E:
            print("Error in MLP: vertex color smooth failed; " + str(E))

        try:
            # needed to make sure VBO is up to date
            ob.data.update()
        except Exception as E:
            print("Error in MLP: VBO ob.data.update failed; " + str(E))

        try:
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.spaces[0].viewport_shade = "TEXTURED"
        except Exception as E:
            print("Error in MLP: view3D viewport shade textured failed; " + str(E))

    try:
        for obj in bpy.context.scene.objects:
            if obj.BBInfo:
                obj.hide = True
                obj.hide_render = True
    except Exception as E:
        print("Error in MLP: obj.BBInfo")
    print("MLP function completed")


def mlpRender(tID):
    print("MLP RENDER Start")

    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_RENDER'
    opSystem = scene.bb25_opSystem
    homePath = scene.bb25_homepath
    blenderPath = scene.bb25_blenderPath

    for obj in bpy.data.objects:
        try:
            if((obj.bb2_pdbID == tID) and (obj.bb2_objectType == "SURFACE")):
                surfaceName = str(copy.copy(obj.name))
        except Exception as E:
            print(str(E))
    ob = bpy.data.objects[surfaceName]

    bpy.ops.object.select_all(action="DESELECT")
    for o in bpy.data.objects:
        o.select = False

    scene.objects.active = None
    bpy.data.objects[surfaceName].select = True

    scene.objects.active = bpy.data.objects[surfaceName]

    # Stop if no surface is found
    if not ob:
        raise Exception("No MLP Surface Found, select surface view first")

    # Stop if no dx data is loaded
    if not dxData:
        raise Exception("No MLP data is loaded.  Run MLP calculation first")

    # create image data block
    try:
        print("MLP Render first time: False")
        firstTime = False
        image = bpy.data.images["MLPBaked"]
    except:
        print("MLP Render first time: True")
        firstTime = True
        image = bpy.data.images.new(name="MLPBaked", width=2048, height=2048)

    # set material
    if firstTime:
        mat = bpy.data.materials.new("matMLP")
        mat.use_shadeless = True
        mat.use_vertex_color_paint = True
        ob.data.materials.append(mat)
    else:
        mat = bpy.data.materials["matMLP"]
        mat.use_shadeless = True
        mat.use_vertex_color_paint = True
        if not ob.data.materials:
            ob.data.materials.append(mat)

    print("Baking MLP textures")

    # save and bake
    image.source = "GENERATED"
    image.generated_height = 2048
    image.generated_width = 2048

    if not ob.data.uv_textures:
        bpy.context.active_object.data.uv_textures.new()
    if bpy.context.mode != "EDIT":
        bpy.ops.object.editmode_toggle()
    # ====
    for uv in ob.data.uv_textures[0].data:
        uv.image = image

    bpy.data.screens['UV Editing'].areas[1].spaces[0].image = bpy.data.images['MLPBaked']

    bpy.ops.uv.smart_project(angle_limit=66, island_margin=0, user_area_weight=0)
    bpy.context.scene.render.bake_type = 'TEXTURE'

    bpy.context.scene.render.use_raytrace = False
    print("===== BAKING... =====")
    bpy.ops.object.bake_image()
    print("=====          ... BAKED! =====")
    bpy.context.scene.render.use_raytrace = True

    if opSystem == "linux":
        os.chdir(quotedPath(homePath + "tmp" + os.sep))
    elif opSystem == "darwin":
        os.chdir(quotedPath(homePath + "tmp" + os.sep))
    else:
        os.chdir(r"\\?\\" + homePath + "tmp" + os.sep)

    print("Image Save Render")
    image.save_render(homePath + "tmp" + os.sep + "MLPBaked.png")
    # copy the needed files
    print("Copy the needed files")
    uriSource = homePath + "data" + os.sep + "noise.png"
    uriDest = homePath + "tmp" + os.sep + "noise.png"

    if opSystem == "linux":
        shutil.copy(uriSource, uriDest)
    elif opSystem == "darwin":
        shutil.copy(uriSource, uriDest)
    else:
        shutil.copy(r"\\?\\" + uriSource, r"\\?\\" + uriDest)

    uriSource = homePath + "data" + os.sep + "composite.blend"
    uriDest = homePath + "tmp" + os.sep + "composite.blend"

    if opSystem == "linux":
        shutil.copy(uriSource, uriDest)
    elif opSystem == "darwin":
        shutil.copy(uriSource, uriDest)
    else:
        shutil.copy(r"\\?\\" + uriSource, r"\\?\\" + uriDest)

    # render out composite texture
    if blenderPath == "":
        bP = quotedPath(str(os.environ['PWD']) + os.sep + "blender")
        command = "%s -b %s -f 1" % (quotedPath(bP), quotedPath(homePath + "tmp" + os.sep + "composite.blend"))
    else:
        command = "%s -b %s -f 1" % (quotedPath(blenderPath), quotedPath(homePath + "tmp" + os.sep + "composite.blend"))

    launch(exeName=command)

    # set materials
    mat.specular_shader = ("TOON")
    mat.specular_toon_size = 0.2
    mat.specular_toon_smooth = 0.0
    mat.specular_intensity = 0.0
    mat.use_shadeless = False
    mat.use_vertex_color_paint = False
    mat.use_shadows = False

    # setup textures
    if firstTime:
        img_bump = bpy.data.images.load(homePath + "tmp" + os.sep + "0001.png")
        tex_bump = bpy.data.textures.new('bump', type="IMAGE")
        tex_bump.image = img_bump
        mtex = mat.texture_slots.add()
        mtex.texture = tex_bump
        mtex.texture_coords = 'UV'
        mtex.use_map_normal = True
        mtex.use_map_color_diffuse = False
        bpy.data.textures["bump"]
        mat.texture_slots[0].normal_factor = 1
        img_baked = bpy.data.images.load(homePath + "tmp" + os.sep + "MLPBaked.png")
        tex_spec = bpy.data.textures.new('specular', type="IMAGE")
        tex_spec.image = img_baked
        tex_spec.contrast = 4.0
        mtex = mat.texture_slots.add()
        mtex.texture = tex_spec
        mtex.texture_coords = 'UV'
        mtex.use_map_color_diffuse = False
        mtex.use_map_specular = True
        mat.texture_slots[1].use_rgb_to_intensity = True
        mat.texture_slots[1].default_value = 1

    # refresh all images
    for img in bpy.data.images:
        img.reload()

    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces[0].viewport_shade = "SOLID"
    bpy.ops.object.editmode_toggle()

    ob.data.materials[0] = mat
    ob.data.materials[0].specular_toon_smooth = 0.3
    ob.data.materials[0].texture_slots[0].normal_factor = 1
    ob.data.materials[0].texture_slots[1].default_value = 1
    ob.data.materials[0].texture_slots[1].specular_factor = 0.1

    bpy.ops.paint.vertex_paint_toggle()
    meshData = ob.data
    vColLayer0 = meshData.vertex_colors[0]
    for vCol in vColLayer0.data:
        vCol.color = Color((
            ((vCol.color[0] - 0.5) * 0.6) + 0.5,
            ((vCol.color[1] - 0.5) * 0.6) + 0.5,
            ((vCol.color[2] - 0.5) * 0.6) + 0.5
        ))
    meshData.update()
    bpy.ops.paint.vertex_paint_toggle()

    ob.data.materials[0].use_vertex_color_paint = True

    for obj in bpy.context.scene.objects:
        if obj.BBInfo:
            obj.hide = True
            obj.hide_render = True


class bb2_operator_atomic_mlp(types.Operator):
    bl_idname = "ops.bb2_operator_atomic_mlp"
    bl_label = "Atomic MLP"
    bl_description = "Atomic MLP"

    def invoke(self, context, event):
        try:
            selectedPDBidS = []
            for b in bpy.context.scene.objects:
                if b.select:
                    try:
                        if(b.bb2_pdbID not in selectedPDBidS):
                            t = copy.copy(b.bb2_pdbID)
                            selectedPDBidS.append(t)
                    except Exception as E:
                        str1 = str(E)   # Do not print...
            context.user_preferences.edit.use_global_undo = False
            for id in selectedPDBidS:
                bpy.ops.object.select_all(action="DESELECT")
                for o in bpy.data.objects:
                    o.select = False
                for obj in bpy.context.scene.objects:
                    try:
                        if obj.bb2_pdbID == id:
                            obj.select = True
                    except Exception as E:
                        str2 = str(E)   # Do not print...
                tID = copy.copy(id)
                atomicMLP(bpy.context.scene.BBAtomicMLP, tID)
            context.user_preferences.edit.use_global_undo = True
        except Exception as E:
            s = "Generate MLP visualization Failed: " + str(E)
            print(s)
            print('Error on line {}'.format(sys.exc_info()[-1].tb_lineno))
            return {'CANCELLED'}
        else:
            return{'FINISHED'}


class bb2_operator_mlp(types.Operator):
    bl_idname = "ops.bb2_operator_mlp"
    bl_label = "Show MLP on Surface"
    bl_description = "Calculate Molecular Lipophilicity Potential on surface"

    def invoke(self, context, event):
        try:

            bpy.context.user_preferences.edit.use_global_undo = False

            selectedPDBidS = []
            for b in bpy.context.scene.objects:
                if b.select:  # == True):
                    try:
                        if(b.bb2_pdbID not in selectedPDBidS):
                            t = copy.copy(b.bb2_pdbID)
                            selectedPDBidS.append(t)
                    except Exception as E:
                        str1 = str(E)   # Do not print...

            context.user_preferences.edit.use_global_undo = False

            for id in selectedPDBidS:
                bpy.ops.object.select_all(action="DESELECT")
                for o in bpy.data.objects:
                    o.select = False
                for obj in bpy.context.scene.objects:
                    try:
                        if obj.bb2_pdbID == id:
                            obj.select = True
                    except Exception as E:
                        str2 = str(E)   # Do not print...

                tID = copy.copy(id)
                print('tID:', tID)

                mlp(tID, force=True)
                todoAndviewpoints()

            bpy.context.scene.BBViewFilter = "4"
            bpy.context.user_preferences.edit.use_global_undo = True

        except Exception as E:
            s = "Generate MLP visualization Failed: " + str(E)
            print(s)
            print('Error on line {}'.format(sys.exc_info()[-1].tb_lineno))
            return {'CANCELLED'}
        else:
            return{'FINISHED'}


class bb2_operator_mlp_render(types.Operator):
    bl_idname = "ops.bb2_operator_mlp_render"
    bl_label = "Render MLP to Surface"
    bl_description = "Visualize Molecular Lipophilicity Potential on surface"

    def invoke(self, context, event):
        try:
            context.user_preferences.edit.use_global_undo = False
            selectedPDBidS = []
            for b in bpy.context.scene.objects:
                if b.select:
                    try:
                        if((b.bb2_pdbID not in selectedPDBidS) and (b.bb2_objectType == "SURFACE")):
                            t = copy.copy(b.bb2_pdbID)
                            selectedPDBidS.append(t)
                    except Exception as E:
                        str1 = str(E)   # Do not print...
            context.user_preferences.edit.use_global_undo = False
            for id in selectedPDBidS:
                tID = copy.copy(id)
                mlpRender(tID)
                todoAndviewpoints()
            context.scene.BBViewFilter = "4"
            context.user_preferences.edit.use_global_undo = True
        except Exception as E:
            s = "Generate MLP visualization Failed: " + str(E)
            print(s)
            return {'CANCELLED'}
        else:
            return{'FINISHED'}


class BB2_MLP_PANEL(types.Panel):
    bl_label = "BioBlender2 MLP Visualization"
    bl_idname = "BB2_MLP_PANEL"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_options = {'DEFAULT_CLOSED'}

    types.Scene.BBAtomic = props.EnumProperty(attr="BBAtomic", name="BBAtomic", description="Atomic or Surface MLP", items=(("0", "Atomic", ""), ("1", "Surface", "")), default="0")
    types.Scene.BBMLPFormula = props.EnumProperty(attr="BBMLPFormula", name="Formula", description="Select a formula for MLP calculation", items=(("0", "Dubost", ""), ("1", "Testa", ""), ("2", "Fauchere", ""), ("3", "Brasseur", ""), ("4", "Buckingham", "")), default="1")
    types.Scene.BBMLPGridSpacing = props.FloatProperty(attr="BBMLPGridSpacing", name="Grid Spacing", description="MLP Calculation step size (Smaller is better, but slower)", default=1, min=0.01, max=20, soft_min=1.4, soft_max=10)
    types.Scene.BBAtomicMLP = props.BoolProperty(attr="BBAtomicMLP", name="Atomic MLP", description="Atomic MLP", default=False)

    def draw(self, context):
        scene = context.scene
        layout = self.layout

        r = layout.row()
        r.prop(scene, "BBAtomic", expand=True)
        r = layout.row()
        if(bpy.context.scene.BBAtomic == "0"):
            r.prop(scene, "BBAtomicMLP")
            r = layout.row()
            r.operator("ops.bb2_operator_atomic_mlp")
        else:
            split = layout.split()
            c = split.column()
            c.prop(scene, "BBMLPFormula")
            c.prop(scene, "BBMLPGridSpacing")
            r = split.row()
            r.scale_y = 2
            r.operator("ops.bb2_operator_mlp")
            split = layout.split()
            r = split.column(align=True)
            r = split.column()
            r.scale_y = 2
            r.operator("ops.bb2_operator_mlp_render")
