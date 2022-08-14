// NOTE: Assertions have been autogenerated by utils/generate-test-checks.py
// RUN: circt-opt %s --convert-llhd-to-llvm | FileCheck %s

// CHECK-LABEL:   llvm.func @driveSignal(!llvm.ptr<i8>, !llvm.ptr<struct<(ptr<i8>, i64, i64, i64)>>, !llvm.ptr<i8>, i64, i64, i64, i64)

// CHECK-LABEL:   llvm.func @Foo(
// CHECK-SAME:                   %[[VAL_0:.*]]: !llvm.ptr<i8>,
// CHECK-SAME:                   %[[VAL_1:.*]]: !llvm.ptr<struct<()>>,
// CHECK-SAME:                   %[[VAL_2:.*]]: !llvm.ptr<struct<(ptr<i8>, i64, i64, i64)>>) {
// CHECK:           %[[VAL_3:.*]] = llvm.mlir.constant(false) : i1
// CHECK:           %[[VAL_4:.*]] = llvm.mlir.constant(0 : i32) : i32
// CHECK:           %[[VAL_5:.*]] = llvm.getelementptr %[[VAL_2]]{{\[}}%[[VAL_4]]] : (!llvm.ptr<struct<(ptr<i8>, i64, i64, i64)>>, i32) -> !llvm.ptr<struct<(ptr<i8>, i64, i64, i64)>>
// CHECK:           %[[VAL_6:.*]] = llvm.mlir.constant(0 : i32) : i32
// CHECK:           %[[VAL_7:.*]] = llvm.mlir.constant(1 : i32) : i32
// CHECK:           %[[VAL_8:.*]] = llvm.getelementptr %[[VAL_5]]{{\[}}%[[VAL_6]], 0] : (!llvm.ptr<struct<(ptr<i8>, i64, i64, i64)>>, i32) -> !llvm.ptr<ptr<i8>>
// CHECK:           %[[VAL_9:.*]] = llvm.load %[[VAL_8]] : !llvm.ptr<ptr<i8>>
// CHECK:           %[[VAL_10:.*]] = llvm.getelementptr %[[VAL_5]]{{\[}}%[[VAL_6]], 1] : (!llvm.ptr<struct<(ptr<i8>, i64, i64, i64)>>, i32) -> !llvm.ptr<i64>
// CHECK:           %[[VAL_11:.*]] = llvm.load %[[VAL_10]] : !llvm.ptr<i64>
// CHECK:           %[[VAL_12:.*]] = llvm.bitcast %[[VAL_9]] : !llvm.ptr<i8> to !llvm.ptr<i16>
// CHECK:           %[[VAL_13:.*]] = llvm.load %[[VAL_12]] : !llvm.ptr<i16>
// CHECK:           %[[VAL_14:.*]] = llvm.trunc %[[VAL_11]] : i64 to i16
// CHECK:           %[[VAL_15:.*]] = llvm.lshr %[[VAL_13]], %[[VAL_14]]  : i16
// CHECK:           %[[VAL_16:.*]] = llvm.trunc %[[VAL_15]] : i16 to i1
// CHECK:           %[[VAL_17:.*]] = llvm.mlir.constant(true) : i1
// CHECK:           %[[VAL_18:.*]] = llvm.xor %[[VAL_16]], %[[VAL_17]]  : i1
// CHECK:           %[[VAL_19:.*]] = llvm.mlir.constant(dense<[1000, 0, 0]> : tensor<3xi64>) : !llvm.array<3 x i64>
// CHECK:           %[[VAL_20:.*]] = llvm.mlir.constant(1 : i64) : i64
// CHECK:           %[[VAL_21:.*]] = llvm.mlir.constant(1 : i32) : i32
// CHECK:           %[[VAL_22:.*]] = llvm.alloca %[[VAL_21]] x i1 {alignment = 4 : i64} : (i32) -> !llvm.ptr<i1>
// CHECK:           llvm.store %[[VAL_18]], %[[VAL_22]] : !llvm.ptr<i1>
// CHECK:           %[[VAL_23:.*]] = llvm.bitcast %[[VAL_22]] : !llvm.ptr<i1> to !llvm.ptr<i8>
// CHECK:           %[[VAL_24:.*]] = llvm.extractvalue %[[VAL_19]][0] : !llvm.array<3 x i64>
// CHECK:           %[[VAL_25:.*]] = llvm.extractvalue %[[VAL_19]][1] : !llvm.array<3 x i64>
// CHECK:           %[[VAL_26:.*]] = llvm.extractvalue %[[VAL_19]][2] : !llvm.array<3 x i64>
// CHECK:           llvm.call @driveSignal(%[[VAL_0]], %[[VAL_5]], %[[VAL_23]], %[[VAL_20]], %[[VAL_24]], %[[VAL_25]], %[[VAL_26]]) : (!llvm.ptr<i8>, !llvm.ptr<struct<(ptr<i8>, i64, i64, i64)>>, !llvm.ptr<i8>, i64, i64, i64, i64) -> ()
// CHECK:           llvm.return
// CHECK:         }

llhd.entity @Foo () -> () {
  %0 = hw.constant 0 : i1
  %toggle = llhd.sig "toggle" %0 : i1
  %1 = llhd.prb %toggle : !llhd.sig<i1>
  %allset = hw.constant 1 : i1
  %2 = comb.xor %1, %allset : i1
  %dt = llhd.constant_time #llhd.time<1ns, 0d, 0e>
  llhd.drv %toggle, %2 after %dt : !llhd.sig<i1>
}
