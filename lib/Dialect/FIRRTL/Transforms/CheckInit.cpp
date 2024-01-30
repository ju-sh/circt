//===- CheckInit.cpp - Ensure all wires are initialized ------*- C++ -*-===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//
//
// This file defines the CheckInit pass.  This pass checks that all wires are
// initialized (connected too).
//
//===----------------------------------------------------------------------===//

#include "PassDetails.h"
#include "circt/Dialect/FIRRTL/FIRRTLFieldSource.h"
#include "llvm/Support/Debug.h"

#define DEBUG_TYPE "firrtl-check-init"

using llvm::BitVector;

using namespace mlir;
using namespace circt;
using namespace firrtl;

static void clearUnder(BitVector &bits, Type t, ArrayRef<int64_t> path,
                       uint64_t fieldBase = 0) {
  if (auto bundle = dyn_cast<BundleType>(t)) {
    if (path.empty()) {
      for (size_t idx = 0, e = bundle.getNumElements(); idx != e; ++idx)
        clearUnder(bits, bundle.getElementType(idx), path,
                   fieldBase + bundle.getFieldID(idx));
    } else {
      clearUnder(bits, bundle.getElementType(path.front()), path.drop_front(),
                 fieldBase + bundle.getFieldID(path.front()));
    }
  } else if (auto bundle = dyn_cast<OpenBundleType>(t)) {
    if (path.empty()) {
      for (size_t idx = 0, e = bundle.getNumElements(); idx != e; ++idx)
        clearUnder(bits, bundle.getElementType(idx), path,
                   fieldBase + bundle.getFieldID(idx));
    } else {
      clearUnder(bits, bundle.getElementType(path.front()), path.drop_front(),
                 fieldBase + bundle.getFieldID(path.front()));
    }
  } else if (auto vec = dyn_cast<FVectorType>(t)) {
    if (path.empty()) {
      for (size_t idx = 0, e = vec.getNumElements(); idx != e; ++idx)
        clearUnder(bits, vec.getElementType(), path,
                   fieldBase + vec.getFieldID(idx));
    } else {
      clearUnder(bits, vec.getElementType(), path.drop_front(),
                 fieldBase + vec.getFieldID(path.front()));
    }
  } else if (auto vec = dyn_cast<OpenVectorType>(t)) {
    if (path.empty()) {
      for (size_t idx = 0, e = vec.getNumElements(); idx != e; ++idx)
        clearUnder(bits, vec.getElementType(), path,
                   fieldBase + vec.getFieldID(idx));
    } else {
      clearUnder(bits, vec.getElementType(), path.drop_front(),
                 fieldBase + vec.getFieldID(path.front()));
    }
  } else {
    assert(bits.size() > fieldBase);
    LLVM_DEBUG({
      llvm::errs() << "found " << fieldBase;
      if (bits[fieldBase])
        llvm::errs() << " needed";
      llvm::errs() << "\n";
    });
    bits.reset(fieldBase);
  }
}

static void markLeaves(BitVector &bits, Type t, bool isPort = false,
                       bool isFlip = false, uint64_t fieldBase = 0) {
  LLVM_DEBUG({
    llvm::errs() << "port:" << isPort << " flip:" << isFlip
                 << " id:" << fieldBase << " ";
    t.dump();
  });
  if (auto bundle = dyn_cast<BundleType>(t)) {
    for (size_t idx = 0, e = bundle.getNumElements(); idx != e; ++idx)
      markLeaves(bits, bundle.getElementType(idx), isPort,
                 isFlip ^ bundle.getElement(idx).isFlip,
                 fieldBase + bundle.getFieldID(idx));
  } else if (auto bundle = dyn_cast<OpenBundleType>(t)) {
    for (size_t idx = 0, e = bundle.getNumElements(); idx != e; ++idx)
      markLeaves(bits, bundle.getElementType(idx), isPort,
                 isFlip ^ bundle.getElement(idx).isFlip,
                 fieldBase + bundle.getFieldID(idx));
  } else if (auto vec = dyn_cast<FVectorType>(t)) {
    for (size_t idx = 0, e = vec.getNumElements(); idx != e; ++idx)
      markLeaves(bits, vec.getElementType(), isPort, isFlip,
                 fieldBase + vec.getFieldID(idx));
  } else if (auto vec = dyn_cast<OpenVectorType>(t)) {
    for (size_t idx = 0, e = vec.getNumElements(); idx != e; ++idx)
      markLeaves(bits, vec.getElementType(), isPort, isFlip,
                 fieldBase + vec.getFieldID(idx));
  } else {
    if (isPort && !isFlip)
      return;
    LLVM_DEBUG({ llvm::errs() << "need " << fieldBase << "\n"; });
    bits.resize(std::max(fieldBase + 1, (uint64_t)bits.size()));
    bits.set(fieldBase);
  }
}

static void markWrite(BitVector& bv, size_t fieldID) {
    if (bv.size() <= fieldID)
        bv.resize(fieldID + 1);
    bv.set(fieldID);
}

namespace {
class CheckInitPass : public CheckInitBase<CheckInitPass> {
  // SetSets track initialized fieldIDs
  using SetSet = DenseMap<Value, BitVector>;
  struct RegionState {
    // Values Inited in this state's regions.  To be intersected.
    SetSet init;
    // Children to merge into this state
    SmallVector<Operation *, 4> children;
    // Definitions from this state
    SmallVector<Value> dests;
  };

  struct OpState {
    SmallVector<RegionState, 2> regions;
  };

  SmallVector<Operation *> worklist;
  DenseMap<Operation *, OpState> localInfo;

  void processOp(Operation *op, FieldSource &fieldSource);

public:
  void runOnOperation() override;
};
} // end anonymous namespace

// compute the values set by op's regions.  A when, for example, ands the init
// set as only fields set on both paths are unconditionally set by the when.
void CheckInitPass::processOp(Operation *op, FieldSource &fieldSource) {
  assert(localInfo.count(op) == 0);
  auto &state = localInfo[op];

  for (auto &region : op->getRegions()) {
    auto &local = state.regions.emplace_back();
    for (auto &block : region) {
      for (auto &opref : block) {
        Operation *op = &opref;
        if (auto wire = dyn_cast<WireOp>(op)) {
          local.dests.push_back(wire.getResult());
        } else if (isa<RegOp, RegResetOp>(op)) {
          local.dests.push_back(op->getResult(0));
        } else if (auto mem = dyn_cast<MemOp>(op)) {
          for (auto result : mem.getResults())
            local.dests.push_back(result);
        } else if (auto memport = dyn_cast<chirrtl::MemoryPortOp>(op)) {
          local.dests.push_back(memport.getResult(0));
        } else if (auto inst = dyn_cast<InstanceOp>(op)) {
          for (auto [idx, arg] : llvm::enumerate(inst.getResults()))
            local.dests.push_back(arg);
        } else if (auto inst = dyn_cast<InstanceChoiceOp>(op)) {
          for (auto [idx, arg] : llvm::enumerate(inst.getResults()))
            local.dests.push_back(arg);
        } else if (auto con = dyn_cast<ConnectOp>(op)) {
          auto node = fieldSource.nodeForValue(con.getDest());
          markWrite(local.init[node.src], node.fieldID);
        } else if (auto con = dyn_cast<StrictConnectOp>(op)) {
          auto node = fieldSource.nodeForValue(con.getDest());
          markWrite(local.init[node.src], node.fieldID);
        } else if (auto def = dyn_cast<RefDefineOp>(op)) {
          auto node = fieldSource.nodeForValue(def.getDest());
          markWrite(local.init[node.src], node.fieldID);
        } else if (isa<WhenOp, MatchOp>(op)) {
          local.children.push_back(op);
        }
      }
    }
  }
}

void CheckInitPass::runOnOperation() {
  auto &fieldSource = getAnalysis<FieldSource>();
  worklist.push_back(getOperation());

  // Each op should only be able to be inserted in the worklist once, so don't
  // worry about keeping track of visited operations.
  while (!worklist.empty()) {
    Operation *op = worklist.back();
    worklist.pop_back();
    processOp(op, fieldSource);
  }

  // Modules are the only blocks with arguments, so capture them here only.
  auto& topLevel = localInfo[getOperation()];
  for (auto arg :
       getOperation().getBodyBlock()->getArguments())
    topLevel.regions[0].dests.push_back(arg);
}

std::unique_ptr<mlir::Pass> circt::firrtl::createCheckInitPass() {
  return std::make_unique<CheckInitPass>();
}
