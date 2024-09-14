// RUN: circt-opt -firrtl-add-seqmem-ports -verify-diagnostics -split-input-file %s

// expected-error@below {{MetadataDirAnnotation requires field 'dirname' of string type}}
firrtl.circuit "Simple" attributes {annotations = [{
    class = "sifive.enterprise.firrtl.MetadataDirAnnotation"
  }]} {
  firrtl.module @Simple() {}
}

// -----

// expected-error@below {{AddSeqMemPortsFileAnnotation requires field 'filename' of string type}}
firrtl.circuit "Simple" attributes {annotations = [{
    class = "sifive.enterprise.firrtl.AddSeqMemPortsFileAnnotation"
  }]} {
  firrtl.module @Simple() {}
}

// -----

// expected-error@below {{circuit has two AddSeqMemPortsFileAnnotation annotations}}
firrtl.circuit "Simple" attributes {annotations = [
  {
    class = "sifive.enterprise.firrtl.AddSeqMemPortsFileAnnotation",
    filename = "test"
  },
  {
    class = "sifive.enterprise.firrtl.AddSeqMemPortsFileAnnotation",
    filename = "test"
  }]} {
  firrtl.module @Simple() {}
}

// -----

// expected-error@below {{AddSeqMemPortAnnotation requires field 'name' of string type}}
firrtl.circuit "Simple" attributes {annotations = [{
  class = "sifive.enterprise.firrtl.AddSeqMemPortAnnotation",
  input = true,
  width = 5
 }]} {
  firrtl.module @Simple() { }
}

// -----

// expected-error@below {{AddSeqMemPortAnnotation requires field 'input' of boolean type}}
firrtl.circuit "Simple" attributes {annotations = [{
  class = "sifive.enterprise.firrtl.AddSeqMemPortAnnotation",
  name = "user_input",
  width = 5
 }]} {
  firrtl.module @Simple() { }
}

// -----

// expected-error@below {{AddSeqMemPortAnnotation requires field 'width' of integer type}}
firrtl.circuit "Simple" attributes {annotations = [{
  class = "sifive.enterprise.firrtl.AddSeqMemPortAnnotation",
  name = "user_input",
  input = true
 }]} {
  firrtl.module @Simple() { }
}

// -----

firrtl.circuit "Foo" attributes {
  annotations = [
    {
      class = "sifive.enterprise.firrtl.AddSeqMemPortAnnotation",
      name = "user_input",
      input = false,
      width = 1
    }
  ]
} {
  firrtl.layer @A bind {}

  // expected-error @below {{cannot have an output port added to it because it is instantiated under a layer block}}
  firrtl.memmodule @mem_ext(
    in W0_addr: !firrtl.uint<1>,
    in W0_en: !firrtl.uint<1>,
    in W0_clk: !firrtl.clock,
    in W0_data: !firrtl.uint<1>
  ) attributes {
    dataWidth = 1 : ui32,
    depth = 2 : ui64,
    extraPorts = [],
    maskBits = 1 : ui32,
    numReadPorts = 0 : ui32,
    numReadWritePorts = 0 : ui32,
    numWritePorts = 1 : ui32,
    readLatency = 1 : ui32,
    writeLatency = 1 : ui32
  }

  firrtl.module @Foo() {
    // expected-note @below {{the memory is instantiated under this layer block}}
    firrtl.layerblock @A {
      // expected-note @below {{the memory is instantiated here}}
      %0:4 = firrtl.instance MWrite_ext  @mem_ext(
        in W0_addr: !firrtl.uint<1>,
        in W0_en: !firrtl.uint<1>,
        in W0_clk: !firrtl.clock,
        in W0_data: !firrtl.uint<1>
      )
    }
  }

}
