import bpy
from bpy.props import PointerProperty, BoolProperty, StringProperty, FloatProperty, IntProperty, FloatVectorProperty, EnumProperty, CollectionProperty
from bpy.types import PropertyGroup




class HVE_props_make_light(PropertyGroup):
    type: EnumProperty(name="Type",items= [('NOT_A_LIGHT', "Not a light", ""),
                                            ('HVE_HEADLIGHT_LEFT', "Headlight Left", ""),
                                            ('HVE_HEADLIGHT_RIGHT', "Headlight Right", ""), 
                                            ('HVE_REVERSE_LEFT', "Reverse Left", ""), 
                                            ('HVE_REVERSE_RIGHT', "Reverse Right", ""), 
                                            ('HVE_FOGLIGHT_LEFT', "Foglight Left", ""), 
                                            ('HVE_FOGLIGHT_RIGHT', "Foglight Right", ""), 
                                            ('HVE_AMBERTURN_LEFT', "Amber/Turn Left", ""), 
                                            ('HVE_AMBERTURN_RIGHT', "Amber/Turn Right", ""),  
                                            ('HVE_AMBERTAIL_LEFT', "Amber Tail Left", ""),  
                                            ('HVE_AMBERTAIL_RIGHT', "Amber Tail Right", ""),  
                                            ('HVE_BRAKETURN_LEFT', "Brake/Turn Left", ""),  
                                            ('HVE_BRAKETURN_RIGHT', "Brake/Turn Right", ""),
                                            ('HVE_BRAKE_LEFT', "Brake Left", ""),
                                            ('HVE_BRAKE_RIGHT', "Brake Right", ""),
                                            ('HVE_BRAKE_CENTER', "Brake Center", ""),],     
                                   default = 'NOT_A_LIGHT',  
                                   description = "Type of light",)  


                                   
class HVE_lights(PropertyGroup):   
    make_light: PointerProperty(type=HVE_props_make_light, )   
    
    @classmethod
    def register(cls):
        bpy.types.Object.hve_vehicle_light = PointerProperty(type=cls)
    
    @classmethod
    def unregister(cls):
        del bpy.types.Object.hve_vehicle_light
        
        
class HVE_props_set_type(bpy.types.PropertyGroup):
    type: EnumProperty(name="Type",items= [('VEHICLE', "Vehicle", ""),
                                            ('ENVIRONMENT', "Environment", ""),],     
                                   default = 'ENVIRONMENT',  
                                   description = "HVE Vehicle or Environment",)          


class HVE_types(PropertyGroup):   
    set_type: PointerProperty(type=HVE_props_set_type, )    
    
    @classmethod
    def register(cls):
        bpy.types.Object.hve_type = PointerProperty(type=cls)
    
    @classmethod
    def unregister(cls):
        del bpy.types.Object.hve_type

class HVE_props_environment(bpy.types.PropertyGroup):
    poName: bpy.props.StringProperty(name= "Material Name", default="Asphalt, Normal")
    poForceConst: bpy.props.FloatProperty(name= "Force Constant (lb)", default= 5000, min=0)
    poForceLinear: bpy.props.FloatProperty(name= "Linear Stiffness (lb/in)", default= 50000, min=0) 
    poForceQuad: bpy.props.FloatProperty(name= "Quadratic Stiffness (lb/in^2)", default= 1000, min=0) 
    poForceCubic: bpy.props.FloatProperty(name= "Cubic Stiffness (lb/in^3)", default= 1000, min=0)  
    poRateDamping: bpy.props.FloatProperty(name= "Damping Constant (lb-sec/in)", default= 0.5, min=0, soft_max = 1) 
    poFriction: bpy.props.FloatProperty(name= "Friction Multiplier", default= 1, min=0, soft_max = 10)   
    poForceUnload: bpy.props.FloatProperty(name= "Unloading Slope", default= 100000, min=0) 
    poBekkerConst: bpy.props.FloatProperty(name= "Bekker Soil Exponent, N", default= 0, min=0) 
    poKphi: bpy.props.FloatProperty(name= "Frictional Soil Mod (lb/in^N+1)", default= 0, min=0) 
    poKc: bpy.props.FloatProperty(name= "Cohesive Soil Mod (lb/in^N+2)", default= 0, min=0) 
    poPcntMoisture: bpy.props.FloatProperty(name= "Moisture Content (%/100)", default= 0, min=0, max =1)
    poPcntClay: bpy.props.FloatProperty(name= "Macrotexture", default= 0.02, min=0, soft_max = 1) 
    poSurfaceType: bpy.props.EnumProperty(
        name= "Surface_Type",
        description= "Surface_Type",
        items= [('EdTypeRoad', "Road", ""),
                ('EdTypeZone', "Friction Zone", ""),
                ('EdTypeCurb', "Curb", ""),
                ('EdTypeWater', "Water", ""),
                ('EdTypeOther', "Other", "")
        ]
    )
    poWaterDepth: bpy.props.FloatProperty(name= "Water Depth", default= 0, min=0, soft_max = 5) 
    poStaticWater: bpy.props.BoolProperty(
    name="Static Water",
    description="Enable (1) or Disable (0) static water",
    default=True
)
    polabel: bpy.props.StringProperty(name= "Overlay", default="Untitled")
    

    
    
class HVE_env_props(PropertyGroup):   
    set_env_props: PointerProperty(type=HVE_props_environment, )    
    
    @classmethod
    def register(cls):
        bpy.types.Object.hve_env_props = PointerProperty(type=cls)
    
    @classmethod
    def unregister(cls):
        del bpy.types.Object.hve_env_props

class AnimationSettings(PropertyGroup):
    """Property group for CSV Animation settings"""
    EDR_INPUT_MODE_ITEMS = [
        ('YAW_RATE', "Yaw Rate", "Time, Speed, Yaw Rate (deg/s)"),
        ('STEERING_WHEEL_ANGLE', "Steering Wheel Angle", "Time, Speed, Steering Wheel Angle (deg)"),
    ]

    def update_fps(self, context):
        """Ensures that FPS in the scene updates when anim_fps is changed"""
        context.scene.render.fps = self.anim_fps

    def _get_edr_target(self):
        return self.edr_anim_object

    def sync_edr_settings_from_target(self):
        """Load per-object EDR settings for the currently selected EDR target."""
        target = self._get_edr_target()
        if not target:
            return

        stored_mode = getattr(target, "edr_input_mode_preference", None)
        valid_modes = {item[0] for item in self.EDR_INPUT_MODE_ITEMS}
        if stored_mode in valid_modes and self.edr_input_mode != stored_mode:
            self.edr_input_mode = stored_mode

        for scene_prop, object_prop in (
            ("edr_wheelbase", "edr_wheelbase_preference"),
            ("edr_steering_gear_ratio", "edr_steering_gear_ratio_preference"),
            ("edr_use_slip_estimate", "edr_use_slip_estimate_preference"),
            ("edr_slip_gain", "edr_slip_gain_preference"),
            ("edr_slip_max_deg", "edr_slip_max_deg_preference"),
        ):
            stored = getattr(target, object_prop, None)
            if stored is not None and getattr(self, scene_prop) != stored:
                setattr(self, scene_prop, stored)

    def update_edr_anim_object(self, context):
        """Load per-object EDR settings when target object changes."""
        self.sync_edr_settings_from_target()

    def _persist_setting(self, scene_prop, object_prop):
        target = self._get_edr_target()
        if not target:
            return
        target[object_prop] = getattr(self, scene_prop)

    def update_edr_input_mode(self, context):
        """Persist selected EDR input mode onto the active EDR target object."""
        target = self._get_edr_target()
        if not target:
            return
        target.edr_input_mode_preference = self.edr_input_mode

    def update_edr_wheelbase(self, context):
        self._persist_setting("edr_wheelbase", "edr_wheelbase_preference")

    def update_edr_steering_gear_ratio(self, context):
        self._persist_setting("edr_steering_gear_ratio", "edr_steering_gear_ratio_preference")

    def update_edr_use_slip_estimate(self, context):
        self._persist_setting("edr_use_slip_estimate", "edr_use_slip_estimate_preference")

    def update_edr_slip_gain(self, context):
        self._persist_setting("edr_slip_gain", "edr_slip_gain_preference")

    def update_edr_slip_max_deg(self, context):
        self._persist_setting("edr_slip_max_deg", "edr_slip_max_deg_preference")

    anim_object: PointerProperty(
        name="Target Object",
        type=bpy.types.Object,
        description="Legacy shared target object (kept for compatibility)"
    )

    edr_anim_object: PointerProperty(
        name="EDR Target Object",
        type=bpy.types.Object,
        description="Select the object to animate with EDR data",
        update=update_edr_anim_object,
    )

    motion_anim_object: PointerProperty(
        name="Motion Target Object",
        type=bpy.types.Object,
        description="Select the object to animate with motion CSV data"
    )

    anim_fps: IntProperty(
        name="Frame Rate",
        description="Set animation frame rate",
        default=24,
        min=1,
        update=update_fps  # ✅ This ensures FPS updates when changed in the UI
    )

    extrapolation_mode: EnumProperty(
        name="Extrapolation Mode",
        description="Choose how keyframe extrapolation is handled",
        items=[
            ('LINEAR', "Linear", "Set extrapolation mode to 'Linear'"),
            ('CONSTANT', "Constant", "Set extrapolation mode to 'Constant'")
        ],
        default='LINEAR'  # Default selection
    )

    edr_input_mode: EnumProperty(
        name="EDR Input Mode",
        description="Choose whether the third EDR column is yaw rate or steering wheel angle",
        items=EDR_INPUT_MODE_ITEMS,
        default='YAW_RATE',
        update=update_edr_input_mode,
    )

    edr_wheelbase: FloatProperty(
        name="Wheelbase",
        description="Wheelbase used to estimate yaw rate from steering wheel angle and slip approximation",
        default=2.8,
        min=0.001,
        soft_max=10.0,
        unit='LENGTH',
        update=update_edr_wheelbase,
    )

    edr_steering_gear_ratio: FloatProperty(
        name="Steering Gear Ratio",
        description="Steering wheel angle to road wheel angle ratio",
        default=16.0,
        min=0.001,
        soft_max=30.0,
        update=update_edr_steering_gear_ratio,
    )

    edr_use_slip_estimate: BoolProperty(
        name="Use Slip Estimate",
        description="Estimate an apparent body slip angle for translation using speed and the selected EDR mode",
        default=False,
        update=update_edr_use_slip_estimate,
    )

    edr_slip_gain: FloatProperty(
        name="Slip Gain",
        description="Scale factor for estimated slip angle",
        default=1.0,
        min=0.0,
        soft_max=3.0,
        update=update_edr_slip_gain,
    )

    edr_slip_max_deg: FloatProperty(
        name="Slip Max (deg)",
        description="Absolute clamp on estimated slip angle in degrees",
        default=12.0,
        min=0.0,
        soft_max=45.0,
        update=update_edr_slip_max_deg,
    )

    edr_use_slip_estimate: BoolProperty(
        name="Use Slip Estimate",
        description="Estimate an apparent body slip angle for translation using speed and the selected EDR mode",
        default=False,
    )

    edr_slip_gain: FloatProperty(
        name="Slip Gain",
        description="Scale factor for estimated slip angle",
        default=1.0,
        min=0.0,
        soft_max=3.0,
    )

    edr_slip_max_deg: FloatProperty(
        name="Slip Max (deg)",
        description="Absolute clamp on estimated slip angle in degrees",
        default=12.0,
        min=0.0,
        soft_max=45.0,
    )


# Store all classes in a list for batch registration
       

classes = (
    HVE_props_make_light,
    HVE_lights,
    HVE_props_set_type,
    HVE_types,
    HVE_props_environment,
    HVE_env_props,
    AnimationSettings,

)  
      
def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Ensure Scene property is registered
    if not hasattr(bpy.types.Scene, "anim_settings"):
        bpy.types.Scene.anim_settings = PointerProperty(type=AnimationSettings)

def unregister():
    if hasattr(bpy.types.Scene, "anim_settings"):
        del bpy.types.Scene.anim_settings

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
