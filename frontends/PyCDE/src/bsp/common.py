#  Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
#  See https://llvm.org/LICENSE.txt for license information.
#  SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception

from __future__ import annotations
from msilib import Control
from turtle import write_docstringdict

from ..behavioral import If
from ..common import Clock, Input, Output
from ..constructs import ControlReg, Mux, NamedWire, Reg, Wire
from .. import esi
from ..module import Module, generator
from ..signals import BundleSignal
from ..types import Array, Bits, ChannelDirection

from typing import Dict, Tuple

MagicNumberLo = 0xE5100E51  # ESI__ESI
MagicNumberHi = 0x207D98E5  # Random
VersionNumber = 0  # Version 0: format subject to change


class ESI_Manifest_ROM(Module):
  """Module which will be created later by CIRCT which will contain the
  compressed manifest."""

  module_name = "__ESI_Manifest_ROM"

  clk = Clock()
  address = Input(Bits(30))
  # Data is two cycles delayed after address changes.
  data = Output(Bits(32))


class AxiMMIO(esi.ServiceImplementation):
  """MMIO service implementation with an AXI-lite protocol. This assumes a 20
  bit address bus for 1MB of addressable MMIO space. Which should be fine for
  now, though nothing should assume this limit. It also only supports 32-bit
  aligned accesses and just throws awary the lower two bits of address.

  Only allows for one outstanding request at a time. If a client doesn't return
  a response, the MMIO service will hang. TODO: add some kind of timeout.

  Implementation-defined MMIO layout:
    - 0x00 (RO): 0 constanst
    - 0x04 (RO): 0 constanst
    - 0x08 (RO): Magic number low (0xE5100E51)
    - 0x0C (RO): Magic number high (random constant: 0x207D98E5)
    - 0x10 (RO): ESI version number (0)
    - 0x14 (RO): Location of the manifest ROM (absolute address)
    - 0x18 (WO): Host memory address to which to write the memory (64 bit). Must
                 write separately to the low (0x18) and high part (0x1C) to
                 initiate the write.

    - 0x100: Start of MMIO space for requests. Mapping is contained in the
             manifest so can be dynamically queried.


    - addr(Manifest ROM) + 0: Size of compressed manifest
    - addr(Manifest ROM) + 4: Start of compressed manifest

  This layout _should_ be pretty standard, but different BSPs may have various
  different restrictions.
  """

  clk = Clock()
  rst = Input(Bits(1))

  # MMIO read: address channel.
  arvalid = Input(Bits(1))
  arready = Output(Bits(1))
  araddr = Input(Bits(20))

  # MMIO read: data response channel.
  rvalid = Output(Bits(1))
  rready = Input(Bits(1))
  rdata = Output(Bits(32))
  rresp = Output(Bits(2))

  # MMIO write: address channel.
  awvalid = Input(Bits(1))
  awready = Output(Bits(1))
  awaddr = Input(Bits(20))

  # MMIO write: data channel.
  wvalid = Input(Bits(1))
  wready = Output(Bits(1))
  wdata = Input(Bits(32))

  # MMIO write: write response channel.
  bvalid = Output(Bits(1))
  bready = Input(Bits(1))
  bresp = Output(Bits(2))

  # Start at this address for assigning MMIO addresses to service requests.
  initial_offset: int = 0x100

  # Manifest DMA write address offset.
  manifest_offset: int = 0x18

  @generator
  def generate(self, bundles: esi._ServiceGeneratorBundles):
    read_table, write_table, manifest_loc = AxiMMIO.build_table(self, bundles)
    AxiMMIO.build_read(self, manifest_loc, read_table)
    AxiMMIO.build_write(self, write_table)
    return True

  def build_table(
      self,
      bundles) -> Tuple[Dict[int, BundleSignal], Dict[int, BundleSignal], int]:
    """Build a table of read and write addresses to BundleSignals."""
    offset = AxiMMIO.initial_offset
    read_table = {}
    write_table = {}
    for bundle in bundles.to_client_reqs:
      if bundle.direction == ChannelDirection.Input:
        read_table[offset] = bundle
        offset += 4
      elif bundle.direction == ChannelDirection.Output:
        write_table[offset] = bundle
        offset += 4

    manifest_loc = 1 << offset.bit_length()
    return read_table, write_table, manifest_loc

  def build_read(self, manifest_loc: int, bundles):
    """Builds the read side of the MMIO service."""

    # Currently just exposes the header and manifest. Not any of the possible
    # service requests.

    i32 = Bits(32)
    i2 = Bits(2)
    i1 = Bits(1)

    address_written = NamedWire(i1, "address_written")
    response_written = NamedWire(i1, "response_written")

    # Only allow one outstanding request at a time. Don't clear it until the
    # output has been transmitted. This way, we don't have to deal with
    # backpressure.
    req_outstanding = ControlReg(self.clk,
                                 self.rst, [address_written],
                                 [response_written],
                                 name="req_outstanding")
    self.arready = ~req_outstanding

    # Capture the address if a the bus transaction occured.
    address_written.assign(self.arvalid & ~req_outstanding)
    address = self.araddr.reg(self.clk, ce=address_written, name="address")
    address_valid = address_written.reg(name="address_valid")
    address_words = address[2:]  # Lop off the lower two bits.

    # Set up the output of the data response pipeline. `data_pipeline*` are to
    # be connected below.
    data_pipeline_valid = NamedWire(i1, "data_pipeline_valid")
    data_pipeline = NamedWire(i32, "data_pipeline")
    data_pipeline_rresp = NamedWire(i2, "data_pipeline_rresp")
    data_out_valid = ControlReg(self.clk,
                                self.rst, [data_pipeline_valid],
                                [response_written],
                                name="data_out_valid")
    self.rvalid = data_out_valid
    self.rdata = data_pipeline.reg(self.clk,
                                   self.rst,
                                   ce=data_pipeline_valid,
                                   name="data_pipeline_reg")
    self.rresp = data_pipeline_rresp.reg(self.clk,
                                         self.rst,
                                         ce=data_pipeline_valid,
                                         name="data_pipeline_rresp_reg")
    # Clear the `req_outstanding` flag when the response has been transmitted.
    response_written.assign(data_out_valid & self.rready)

    # Handle reads from the header (< 0x100).
    header_upper = address_words[AxiMMIO.initial_offset.bit_length() - 2:]
    # Is the address in the header?
    header_sel = (header_upper == header_upper.type(0))
    header_sel.name = "header_sel"
    # Layout the header as an array.
    header = Array(Bits(32), 6)(
        [0, 0, MagicNumberLo, MagicNumberHi, VersionNumber, manifest_loc])
    header.name = "header"
    header_response_valid = address_valid  # Zero latency read.
    header_out = header[address[2:5]]
    header_out.name = "header_out"
    header_rresp = i2(0)

    # Handle reads from the manifest.
    rom_address = NamedWire(
        (address_words.as_uint() - (manifest_loc >> 2)).as_bits(30),
        "rom_address")
    self.mani_rom = ESI_Manifest_ROM(clk=self.clk, address=rom_address)
    mani_valid = address_valid.reg(
        self.clk,
        self.rst,
        rst_value=i1(0),
        cycles=2,  # Two cycle read to match the ROM latency.
        name="mani_valid_reg")
    mani_rresp = i2(0)
    # mani_sel = (address.as_uint() >= manifest_loc)

    # Mux the output depending on whether or not the address is in the header.
    sel = NamedWire(~header_sel, "sel")
    data_mux_inputs = [header_out, self.mani_rom.data]
    data_pipeline.assign(Mux(sel, *data_mux_inputs))
    data_valid_mux_inputs = [header_response_valid, mani_valid]
    data_pipeline_valid.assign(Mux(sel, *data_valid_mux_inputs))
    rresp_mux_inputs = [header_rresp, mani_rresp]
    data_pipeline_rresp.assign(Mux(sel, *rresp_mux_inputs))

  def build_manifest_write(self):
    assert hasattr(self, "mani_rom")

    trigger_write = Wire(Bits(1), "trigger_write")

    # Capture the low 32 bits of the address to write to.
    is_write_lo = (self.awaddr == self.manifest_offset) & self.awvalid
    addr_lo = self.awaddr.reg(self.clk, ce=is_write_lo, name="addr_lo")
    addr_lo_valid = ControlReg(self.clk,
                               self.rst, [is_write_lo], [trigger_write],
                               name="addr_lo_valid")

    # Capture the high 32 bits of the address to write to.
    is_write_hi = (self.awaddr == (self.manifest_offset + 0x4)) & self.awvalid
    addr_hi = self.awaddr.reg(self.clk, ce=is_write_lo, name="addr_hi")
    addr_hi_valid = ControlReg(self.clk,
                               self.rst, [is_write_hi], [trigger_write],
                               name="addr_hi_valid")

    trigger_write.assign(addr_lo_valid & addr_hi_valid)

    write_done = Wire(Bits(1), "write_done")
    writing = ControlReg(self.clk,
                         self.rst, [trigger_write], [write_done],
                         name="writing")

  def build_write(self, bundles):
    self.build_manifest_write()

    # TODO: this.

    # So that we don't wedge the AXI-lite for writes, just ack all of them.
    write_happened = Wire(Bits(1))
    latched_aw = ControlReg(self.clk, self.rst, [self.awvalid],
                            [write_happened])
    latched_w = ControlReg(self.clk, self.rst, [self.wvalid], [write_happened])
    write_happened.assign(latched_aw & latched_w)

    self.awready = 1
    self.wready = 1
    self.bvalid = write_happened
    self.bresp = 0


def AxiHostMemoryService(AddressWidth=64, DataWidth=64, IDWidth=6):

  class AxiHostMemoryService(esi.ServiceImplementation):
    """Service implementation for a host memory service with an AXI protocol."""

    clk = Clock()
    rst = Input(Bits(1))

    #########################
    # AXI4 master interface

    # Address write channel
    AWVALID = Output(Bits(1))
    AWREADY = Input(Bits(1))
    AWADDR = Output(Bits(AddressWidth))
    AWID = Output(Bits(IDWidth))
    AWLEN = Output(Bits(8))
    AWSIZE = Output(Bits(3))
    AWBURST = Output(Bits(2))
    AWLOCK = Output(Bits(2))
    AWCACHE = Output(Bits(4))
    AWPROT = Output(Bits(3))
    AWQOS = Output(Bits(4))
    AWREGION = Output(Bits(4))

    # Data write channel
    WVALID = Output(Bits(1))
    WREADY = Input(Bits(1))
    WDATA = Output(Bits(DataWidth))
    WSTRB = Output(Bits(DataWidth // 8))
    WLAST = Output(Bits(1))

    # Write response channel
    BVALID = Input(Bits(1))
    BREADY = Output(Bits(1))
    BRESP = Input(Bits(2))
    BID = Input(Bits(IDWidth))

    # Address read channel
    ARVALID = Output(Bits(1))
    ARREADY = Input(Bits(1))
    ARADDR = Output(Bits(AddressWidth))
    ARID = Output(Bits(IDWidth))
    ARLEN = Output(Bits(8))
    ARSIZE = Output(Bits(3))
    ARBURST = Output(Bits(2))
    ARLOCK = Output(Bits(2))
    ARCACHE = Output(Bits(4))
    ARPROT = Output(Bits(3))
    ARQOS = Output(Bits(4))
    ARREGION = Output(Bits(4))

    # Read data channel
    RVALID = Input(Bits(1))
    RREADY = Output(Bits(1))
    RDATA = Input(Bits(DataWidth))
    RLAST = Input(Bits(1))
    RID = Input(Bits(IDWidth))
    RRESP = Input(Bits(2))

    @generator
    def build(ports, bundles: esi._ServiceGeneratorBundles):
      ports.AWVALID = 0
      ports.AWADDR = 0
      ports.AWID = 0
      ports.AWLEN = 0
      ports.AWSIZE = 0
      ports.AWBURST = 0
      ports.AWLOCK = 0
      ports.AWCACHE = 0
      ports.AWPROT = 0
      ports.AWQOS = 0
      ports.AWREGION = 0
      ports.WVALID = 0
      ports.WDATA = 0
      ports.WSTRB = 0
      ports.WLAST = 0
      ports.BREADY = 0
      ports.ARVALID = 0
      ports.ARADDR = 0
      ports.ARID = 0
      ports.ARLEN = 0
      ports.ARSIZE = 0
      ports.ARBURST = 0
      ports.ARLOCK = 0
      ports.ARCACHE = 0
      ports.ARPROT = 0
      ports.ARQOS = 0
      ports.ARREGION = 0
      ports.RREADY = 0

      assert len(bundles.to_client_reqs) == 0

  return AxiHostMemoryService
