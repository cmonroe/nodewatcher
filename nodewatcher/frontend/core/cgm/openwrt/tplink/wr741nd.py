from frontend.registry.cgm import base as cgm_base
from frontend.registry.cgm import routers as cgm_routers
from frontend.registry.cgm import protocols as cgm_protocols

class TPLinkWR741ND(cgm_routers.RouterBase):
  """
  TP-Link WR741ND device descriptor.
  """
  identifier = "wr741nd"
  name = "WR741ND"
  manufacturer = "TP-Link"
  url = "http://www.tp-link.com/"
  architecture = "ar71xx"
  radios = [
    cgm_routers.IntegratedRadio("wifi0", "Wifi0", [cgm_protocols.IEEE80211BG, cgm_protocols.IEEE80211N], [
      cgm_routers.AntennaConnector("a1", "Antenna0")
    ])
  ]
  ports = [
    cgm_routers.EthernetPort("wan0", "Wan0"),
    cgm_routers.EthernetPort("lan0", "Lan0")
  ]
  antennas = [
    # TODO this information is probably not correct
    cgm_routers.InternalAntenna(
      identifier = "a1",
      polarization = "horizontal",
      angle_horizontal = 360,
      angle_vertical = 75,
      gain = 2
    )
  ]
  
  @cgm_routers.register_module()
  def network(node, cfg):
    """
    Network configuration CGM for TP-Link WR741ND.
    """
    pass

# Register the TP-Link WR741ND router
cgm_base.register_router("openwrt", TPLinkWR741ND)
