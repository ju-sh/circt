#  Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
#  See https://llvm.org/LICENSE.txt for license information.
#  SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception

from ..common import Clock, Input, Output
from ..module import Module, generator
from ..system import System
from ..types import Bits
from .. import esi

from .common import AxiMMIO, AxiHostMemoryService

import glob
import pathlib
import shutil

__dir__ = pathlib.Path(__file__).parent


def XrtBSP(user_module):
  """Use the Xilinx RunTime (XRT) shell to implement ESI services and build an
  image or emulation package.
  How to use this BSP:
  - Wrap your top PyCDE module in `XrtBSP`.
  - Run your script. This BSP will write a 'build package' to the output dir.
  This package contains a Makefile.xrt.mk which (given a proper Vitis dev
  environment) will compile a hw image or hw_emu image. It is a free-standing
  build package -- you do not need PyCDE installed on the same machine as you
  want to do the image build.
  - To build the `hw` image, run 'make -f Makefile.xrt TARGET=hw'. If you want
  an image which runs on an Azure NP-series instance, run the 'azure' target
  (requires an Azure subscription set up with as per
  https://learn.microsoft.com/en-us/azure/virtual-machines/field-programmable-gate-arrays-attestation).
  This target requires a few environment variables to be set (which the Makefile
  will tell you about).
  - To build a hw emulation image, run with TARGET=hw_emu.
  - Validated ONLY on Vitis 2023.1. Known to NOT work with Vitis <2022.1.
  """

  class XrtTop(Module):
    ap_clk = Clock()
    ap_resetn = Input(Bits(1))

    AddressWidth = 64
    DataWidth = 64
    IDWidth = 6

    # AXI4-Lite slave interface
    s_axi_control_AWVALID = Input(Bits(1))
    s_axi_control_AWREADY = Output(Bits(1))
    s_axi_control_AWADDR = Input(Bits(20))
    s_axi_control_WVALID = Input(Bits(1))
    s_axi_control_WREADY = Output(Bits(1))
    s_axi_control_WDATA = Input(Bits(32))
    s_axi_control_WSTRB = Input(Bits(32 // 8))
    s_axi_control_ARVALID = Input(Bits(1))
    s_axi_control_ARREADY = Output(Bits(1))
    s_axi_control_ARADDR = Input(Bits(20))
    s_axi_control_RVALID = Output(Bits(1))
    s_axi_control_RREADY = Input(Bits(1))
    s_axi_control_RDATA = Output(Bits(32))
    s_axi_control_RRESP = Output(Bits(2))
    s_axi_control_BVALID = Output(Bits(1))
    s_axi_control_BREADY = Input(Bits(1))
    s_axi_control_BRESP = Output(Bits(2))

    #########################
    # AXI4 master interface

    # Address write channel
    m_axi_gmem_AWVALID = Output(Bits(1))
    m_axi_gmem_AWREADY = Input(Bits(1))
    m_axi_gmem_AWADDR = Output(Bits(AddressWidth))
    m_axi_gmem_AWID = Output(Bits(IDWidth))
    m_axi_gmem_AWLEN = Output(Bits(8))
    m_axi_gmem_AWSIZE = Output(Bits(3))
    m_axi_gmem_AWBURST = Output(Bits(2))
    m_axi_gmem_AWLOCK = Output(Bits(2))
    m_axi_gmem_AWCACHE = Output(Bits(4))
    m_axi_gmem_AWPROT = Output(Bits(3))
    m_axi_gmem_AWQOS = Output(Bits(4))
    m_axi_gmem_AWREGION = Output(Bits(4))

    # Data write channel
    m_axi_gmem_WVALID = Output(Bits(1))
    m_axi_gmem_WREADY = Input(Bits(1))
    m_axi_gmem_WDATA = Output(Bits(DataWidth))
    m_axi_gmem_WSTRB = Output(Bits(DataWidth // 8))
    m_axi_gmem_WLAST = Output(Bits(1))

    # Write response channel
    m_axi_gmem_BVALID = Input(Bits(1))
    m_axi_gmem_BREADY = Output(Bits(1))
    m_axi_gmem_BRESP = Input(Bits(2))
    m_axi_gmem_BID = Input(Bits(IDWidth))

    # Address read channel
    m_axi_gmem_ARVALID = Output(Bits(1))
    m_axi_gmem_ARREADY = Input(Bits(1))
    m_axi_gmem_ARADDR = Output(Bits(AddressWidth))
    m_axi_gmem_ARID = Output(Bits(IDWidth))
    m_axi_gmem_ARLEN = Output(Bits(8))
    m_axi_gmem_ARSIZE = Output(Bits(3))
    m_axi_gmem_ARBURST = Output(Bits(2))
    m_axi_gmem_ARLOCK = Output(Bits(2))
    m_axi_gmem_ARCACHE = Output(Bits(4))
    m_axi_gmem_ARPROT = Output(Bits(3))
    m_axi_gmem_ARQOS = Output(Bits(4))
    m_axi_gmem_ARREGION = Output(Bits(4))

    # Read data channel
    m_axi_gmem_RVALID = Input(Bits(1))
    m_axi_gmem_RREADY = Output(Bits(1))
    m_axi_gmem_RDATA = Input(Bits(DataWidth))
    m_axi_gmem_RLAST = Input(Bits(1))
    m_axi_gmem_RID = Input(Bits(IDWidth))
    m_axi_gmem_RRESP = Input(Bits(2))

    @generator
    def construct(ports):
      System.current().platform = "fpga"

      rst = ~ports.ap_resetn

      xrt_mmio = AxiMMIO(
          esi.MMIO,
          appid=esi.AppID("xrt_mmio"),
          clk=ports.ap_clk,
          rst=rst,
          awvalid=ports.s_axi_control_AWVALID,
          awaddr=ports.s_axi_control_AWADDR,
          wvalid=ports.s_axi_control_WVALID,
          wdata=ports.s_axi_control_WDATA,
          wstrb=ports.s_axi_control_WSTRB,
          arvalid=ports.s_axi_control_ARVALID,
          araddr=ports.s_axi_control_ARADDR,
          rready=ports.s_axi_control_RREADY,
          bready=ports.s_axi_control_BREADY,
      )

      # AXI-Lite control
      ports.s_axi_control_AWREADY = xrt_mmio.awready
      ports.s_axi_control_WREADY = xrt_mmio.wready
      ports.s_axi_control_ARREADY = xrt_mmio.arready
      ports.s_axi_control_RVALID = xrt_mmio.rvalid
      ports.s_axi_control_RDATA = xrt_mmio.rdata
      ports.s_axi_control_RRESP = xrt_mmio.rresp
      ports.s_axi_control_BVALID = xrt_mmio.bvalid
      ports.s_axi_control_BRESP = xrt_mmio.bresp

      xrt_hostmem = AxiHostMemoryService(AddressWidth=XrtTop.AddressWidth,
                                         DataWidth=XrtTop.DataWidth,
                                         IDWidth=XrtTop.IDWidth)(
                                             esi.HostMemory,
                                             appid=esi.AppID("xrt_hostmem"),
                                             clk=ports.ap_clk,
                                             rst=rst,
                                             AWREADY=ports.m_axi_gmem_AWREADY,
                                             WREADY=ports.m_axi_gmem_WREADY,
                                             BVALID=ports.m_axi_gmem_BVALID,
                                             BRESP=ports.m_axi_gmem_BRESP,
                                             BID=ports.m_axi_gmem_BID,
                                             ARREADY=ports.m_axi_gmem_ARREADY,
                                             RVALID=ports.m_axi_gmem_RVALID,
                                             RDATA=ports.m_axi_gmem_RDATA,
                                             RLAST=ports.m_axi_gmem_RLAST,
                                             RID=ports.m_axi_gmem_RID,
                                             RRESP=ports.m_axi_gmem_RRESP)
      ports.m_axi_gmem_AWVALID = xrt_hostmem.AWVALID
      ports.m_axi_gmem_AWADDR = xrt_hostmem.AWADDR
      ports.m_axi_gmem_AWID = xrt_hostmem.AWID
      ports.m_axi_gmem_AWLEN = xrt_hostmem.AWLEN
      ports.m_axi_gmem_AWSIZE = xrt_hostmem.AWSIZE
      ports.m_axi_gmem_AWBURST = xrt_hostmem.AWBURST
      ports.m_axi_gmem_AWLOCK = xrt_hostmem.AWLOCK
      ports.m_axi_gmem_AWCACHE = xrt_hostmem.AWCACHE
      ports.m_axi_gmem_AWPROT = xrt_hostmem.AWPROT
      ports.m_axi_gmem_AWQOS = xrt_hostmem.AWQOS
      ports.m_axi_gmem_AWREGION = xrt_hostmem.AWREGION
      ports.m_axi_gmem_WVALID = xrt_hostmem.WVALID
      ports.m_axi_gmem_WDATA = xrt_hostmem.WDATA
      ports.m_axi_gmem_WSTRB = xrt_hostmem.WSTRB
      ports.m_axi_gmem_WLAST = xrt_hostmem.WLAST
      ports.m_axi_gmem_ARVALID = xrt_hostmem.ARVALID
      ports.m_axi_gmem_ARADDR = xrt_hostmem.ARADDR
      ports.m_axi_gmem_ARID = xrt_hostmem.ARID
      ports.m_axi_gmem_ARLEN = xrt_hostmem.ARLEN
      ports.m_axi_gmem_ARSIZE = xrt_hostmem.ARSIZE
      ports.m_axi_gmem_ARBURST = xrt_hostmem.ARBURST
      ports.m_axi_gmem_ARLOCK = xrt_hostmem.ARLOCK
      ports.m_axi_gmem_ARCACHE = xrt_hostmem.ARCACHE
      ports.m_axi_gmem_ARPROT = xrt_hostmem.ARPROT
      ports.m_axi_gmem_ARQOS = xrt_hostmem.ARQOS
      ports.m_axi_gmem_ARREGION = xrt_hostmem.ARREGION
      ports.m_axi_gmem_RREADY = xrt_hostmem.RREADY
      ports.m_axi_gmem_BREADY = xrt_hostmem.BREADY

      user_module(clk=ports.ap_clk, rst=rst)

      # Copy additional sources
      sys: System = System.current()
      sys.add_packaging_step(esi.package)
      sys.add_packaging_step(XrtTop.package)

    @staticmethod
    def package(sys: System):
      """Assemble a 'build' package which includes all the necessary build
      collateral (about which we are aware), build/debug scripts, and the
      generated runtime."""

      sv_sources = glob.glob(str(__dir__ / '*.sv'))
      tcl_sources = glob.glob(str(__dir__ / '*.tcl'))
      for source in sv_sources + tcl_sources:
        shutil.copy(source, sys.hw_output_dir)

      shutil.copy(__dir__ / "Makefile.xrt.mk",
                  sys.output_directory / "Makefile.xrt.mk")
      shutil.copy(__dir__ / "xrt_package.tcl",
                  sys.output_directory / "xrt_package.tcl")
      shutil.copy(__dir__ / "xrt.ini", sys.output_directory / "xrt.ini")
      shutil.copy(__dir__ / "xsim.tcl", sys.output_directory / "xsim.tcl")

  return XrtTop
