ZigZag Hedge 2 Levels Fixed — เอกสาร Logic
ไฟล์: 
ZigZag_Hedge_2Levels_Fixed.mq5
Version: 1.08
ว
ันที่จัดทำ: 6 มีนาคม 2026
ภาพรวม (Overview)
EA นี้ทำงานโดยเปิด position BUY/SELL แรกที่ตลาด แล้ววาง pending order ฝั่งตรงข้ามไว้ระหว่างสองระดับ
(Upper/Lower) ห่างกัน 
InpStepPoints points ต่อเนื่องกันไปเรื่อยๆ พร้อม lot progression และมีระบบป้องกันความ
เสี่ยงหลายชั้น
Flow หลัก:
StartSequence()
└─ 
เปด
 BUY 
หรือ
 SELL 
ที่ตลาด
 → PlaceOppositeStop()
└─ 
วาง
 SELL STOP (
หลัง
 BUY) 
หรือ
 BUY STOP (
หลัง
 SELL)
OnTradeTransaction() → pending 
ถูก
 fill
└─ update state → PlaceOppositeStop() 
ฝงตรงขาม
  ← 
วนซ้ํา
OnTick() / OnTimer()
└─ MaintainOppositePending() — 
ดูแล
 pending 
อยู่เสมอ
└─ CheckProfitLossCloseAll() — 
ปดหมดถาถึงเปา
└─ HandleMarketOpenClose() — deferred close 
เมื่อตลาดกลับมา
1/14
f
ile:///Users/dev/Documents/EA/ZiGZaG/ZigZag_Hedge_2Levels_Fixed_Documentation.html
Input Parameters สำคัญ
Parameter Default ความหมาย
InpAutoStart true เริ่ม EA อัตโนมัติเมื่อ attach
InpStartLot 0.10 Lot ของ position แรก
InpABCDStartMode USE_ABCD_ELSE_BUY ทิศทางเริ่มต้น (BUY เสมอ / ใช้
ABCD / บังคับ ABCD)
InpStepPoints 300 ระยะห่างระหว่าง Upper/Lower level
(points)
InpLotMode LOT_ADD รูปแบบ lot: ADD (เพิ่มทีละ step) หรือ
MUL (คูณ)
InpLotAdd 0.10 ขนาดที่เพิ่มแต่ละ leg ในโหมด ADD
InpLotMultiplier 2.0 ตัวคูณในโหมด MUL
InpMaxCycles 0 จำนวน leg สูงสุด (0 = ไม่จำกัด)
InpCloseAllOnProfit false ปิดทั้งหมดเมื่อกำไรถึง target
InpProfitTargetMoney 50.0 เป้ากำไร (สกุลเงินบัญชี)
InpCloseAllOnLoss false ปิดทั้งหมดเมื่อขาดทุนถึงลิมิต
InpLossLimitMoney-200.0 ลิมิตขาดทุน (เป็นลบ)
InpMagic 20260210 Magic number ของ EA
InpSidewayMinATRPoints 0 ATR ต่ำกว่านี้ = sideways → หยุด
เปิด pending
InpMaxLotLimit 0.0 cap lot สูงสุด (0 = ไม่จำกัด)
InpFollowPriceForPending false ขยับ pending ตาม price ปัจจุบัน
InpUseTerminalGlobalVar true บันทึก state ใน GlobalVariables
3/6/26, 9:18 PM ZigZag Hedge 2 Levels Fixed — เอกสาร Logic
file:///Users/dev/Documents/EA/ZiGZaG/ZigZag_Hedge_2Levels_Fixed_Documentation.html 2/14
โครงสร้าง State Variables
ตัวแปร ประเภท ความหมาย
gUpperPrice double ราคาระดับบน (Upper level)
gLowerPrice double ราคาระดับล่าง (Lower level)
gLastTriggered ZZ_SIDE ฝั่งสุดท้ายที่ถูก fill (BUY/SELL/NONE)
gNextLot double Lot ที่จะใช้กับ pending ถัดไป
gCycles int จำนวน leg ที่เกิดขึ้นแล้ว
gStarted bool EA เริ่มทำงานแล้วหรือยัง
gPendingCloseAll bool ธง: มีคำสั่งปิดทั้งหมดรอตลาดเปิดอยู่
gMarketWasClosed bool ใช้ detect ว่าตลาดเพิ่ง reopen
gAbcdSignal ABCD_SIGNAL สัญญาณ ABCD ล่าสุด (BUY/SELL/NONE)
gPausedBySideway bool ธง: หยุดชั่วคราวเพราะ ATR ต่ำ (sideways)
gPausedByMaxLot bool ธง: หยุดชั่วคราวเพราะ lot เกิน cap
กลุ่มฟังก์ชัน
กลุ่ม 1 — Utility / Setup
DPrint(msg)
Print log เฉพาะเมื่อ InpDebugPrint = true
LotAddShadowEnabled()
คืน true ถ้า shadow lot mode เปิดอยู่ ( InpLotAddShadowEnabled && lot > 0 )
3/6/26, 9:18 PM ZigZag Hedge 2 Levels Fixed — เอกสาร Logic
file:///Users/dev/Documents/EA/ZiGZaG/ZigZag_Hedge_2Levels_Fixed_Documentation.html 3/14
3/6/26, 9:18 PM
ZigZag Hedge 2 Levels Fixed — เอกสาร Logic
LotAddShadowMagic()
ค
ืน magic number ของ shadow EA (ค่า input หรือ 
InpMagic + 1 ถ้าไม่ได้ตั้ง)
BuildLotAddCfg()
สร้าง struct 
LotAddConfig รวม settings ทั้งหมดของ shadow module และ sideway counter
GVName(key)
สร้างชื่อ GlobalVariable แบบ unique ต่อ Symbol + Magic เช่น 
SaveState()
ZZH2LV8_EURUSD_20260210_upper
บ
ันทึก 
gUpperPrice , 
gLowerPrice , 
gNextLot , 
gCycles , 
gLastTriggered , 
gPendingCloseAll ลง Terminal GlobalVariables
LoadState()
gStarted ,
โหลด state กลับมาจาก GlobalVariables (ใช้หลัง EA restart หรือ chart reload)
NormalizeLot(lots)
Normalize lot ให้ตรงข้อกำหนดโบรก: ปรับตาม 
SYMBOL_VOLUME_MIN , 
SYMBOL_VOLUME_STEP
PriceByPoints(price, points, up)
SYMBOL_VOLUME_MAX ,
ค
ำนวณ 
price ± (points × _Point)
IsHedgingAccount()
ตรวจว่าบัญชีเป็น 
ACCOUNT_MARGIN_MODE_RETAIL_HEDGING ซึ่ง EA ต้องการ
IsTradeAllowedNow()
ตรวจรวม 4 เงื่อนไข: 1. Terminal อนุญาต trade 2. EA (MQL) อนุญาต trade 3. Symbol trade mode ไม่ใช่
DISABLED หรือ CLOSEONLY 4. EA ไม่ถูก stop ด้วย 
IsStopped()
4/14
f
ile:///Users/dev/Documents/EA/ZiGZaG/ZigZag_Hedge_2Levels_Fixed_Documentation.html
3/6/26, 9:18 PM
ZigZag Hedge 2 Levels Fixed — เอกสาร Logic
IsFlatNow()
ค
ืน true ถ้าไม่มี positions เปิดอยู่เลย (ทั้ง main + shadow magic)
ResetSequenceStateIfFlat(reason)
ถ
้า flat → ยกเลิก pending ทั้งหมด และ reset: 
gStarted , 
gCycles , 
gLowerPrice , 
gNextLot , 
gPendingCloseAll
PendingRepriceThresholdPts()
gLastTriggered , 
gUpperPrice ,
ค
ืน threshold (points) สำหรับ reprice pending: ใช้ 
InpPendingRepriceThresholdPoints หรือ auto =
max(Step/5, 10)
ShouldRepricePendingNow()
Throttle reprice ให้รันอย่างมาก 1 ครั้งต่อ bar เพื่อลด noise
DesiredOppositePendingPrice(lastSide)
ค
ำนวณราคา pending ที่ต้องการในโหมด 
InpFollowPriceForPending : - หลัง BUY: SELL STOP = bid 
StepPoints - หลัง SELL: BUY STOP = ask + StepPoints
กลุ่ม 2 — Anti-Sideway / ATR Guard
EnsureAtrHandle()
สร้าง handle 
iATR ครั้งแรกที่ใช้งาน (lazy init)
CurrentATRPoints()
อ
่านค่า ATR bar ที่แล้วเสร็จล่าสุด (shift=1) แปลงเป็น points
IsSidewayNow()
ค
ืน true ถ้า 
ATR_points < InpSidewayMinATRPoints
Cache ผลลัพธ์ต่อ bar เพื่อประสิทธิภาพ
เมื่อ sideways: EA จะหยุดวาง pending ใหม่
5/14
f
ile:///Users/dev/Documents/EA/ZiGZaG/ZigZag_Hedge_2Levels_Fixed_Documentation.html
3/6/26, 9:18 PM
ZigZag Hedge 2 Levels Fixed — เอกสาร Logic
ApplyMaxLotLimit(lots, &exceeded)
ถ
้า 
InpMaxLotLimit > 0 และ lot เกิน: cap ที่ limit และตั้ง flag 
exceeded = true
กลุ่ม 3 — ABCD Structure-Break Signal (ZigZag)
ใช้ ZigZag indicator เพื่อหา pivot 4 จุดล่าสุด (A, B, C, D) แล้วระบุทิศทางเริ่มต้นของ sequence
ร
ูปแบบ ABCD
Bullish (→ 
เริ่ม
 BUY):
A(high) → B(low) → C(lower high) → D(lower low)
Bearish (→ 
เริ่ม
 SELL):
A(low) → B(high) → C(higher low) → D(higher high)
ABCD_TF()
Resolve timeframe ที่ใช้: 
InpABCDTimeframe หรือ 
EnsureZigZagHandle()
_Period ถ้าตั้งเป็น CURRENT
สร้าง 
iCustom handle ด้วย path 
InpZigZagPath (lazy init)
DetectLast4Pivots(A, B, C, D)
1. CopyBuffer ZigZag ย้อนหลัง 
InpABCDLookbackBars bars
2. ข้าม 
InpABCDConfirmBars bars แรก (ลด repaint)
3. หา 4 pivot ล่าสุด (เรียงจากใหม่มาเก่า: D, C, B, A)
4. ตรวจว่าแต่ละ leg ≥ 
InpABCDMinLegPoints points
5. ตรวจว่า pivot สลับ High/Low ถูกต้อง
ComputeAbcdSignal(A, B, C, D)
ว
ิเคราะห์ pattern → คืน 
ABCD_BUY , 
ABCD_SELL , หรือ 
ABCD_NONE
6/14
f
ile:///Users/dev/Documents/EA/ZiGZaG/ZigZag_Hedge_2Levels_Fixed_Documentation.html
3/6/26, 9:18 PM
ZigZag Hedge 2 Levels Fixed — เอกสาร Logic
UpdateAbcdSignalIfNeeded()
Update 
gAbcdSignal เมื่อ pivot D ใหม่เกิดขึ้น (ตรวจสอบ 1 ครั้ง/bar)
ไม่แตะ positions ที่เปิดอยู่
กลุ่ม 4 — Position Iteration
SelectPosByIndexSafe(index, &ticket)
Select position by index อย่างปลอดภัย ป้องกัน race condition
CountPositionsByMagic()
น
ับ positions ที่มี magic = 
InpMagic และ symbol ตรงกัน
CountPositionsByMagicValue(magic)
น
ับ positions ของ magic number ใดๆ
CountManagedPositions()
น
ับ positions ทั้งหมดที่ EA ดูแล = main + shadow magic
FloatingProfitByMagic()
รวม floating P&L ของทุก positions ที่ EA manage (ใช้คำนวณว่าถึงเป้าหรือยัง)
GetLastPosition(&side, &openPrice, &vol)
หา position ล่าสุดของ main magic (by เวลาเปิดสูงสุด) → คืน side, openPrice, volume
DumpMyPositions()
Print รายละเอียด positions ทั้งหมดสำหรับ debug
7/14
f
ile:///Users/dev/Documents/EA/ZiGZaG/ZigZag_Hedge_2Levels_Fixed_Documentation.html
3/6/26, 9:18 PM
ZigZag Hedge 2 Levels Fixed — เอกสาร Logic
กลุ่ม 5 — Close Positions
CloseAllPositionsByMagic()
ป
ิด positions ทั้งหมดของ main magic
ถ
้าตลาดปิด → ตั้ง 
gPendingCloseAll = true แล้วออกก่อน
ลอง close หลาย pass (สูงสุด 10 รอบ) เพื่อความแน่ใจ
CloseAllPositionsByMagicValue(magic)
ป
ิด positions ของ magic number ที่ระบุ
CloseAllManagedPositions()
ป
ิดทั้ง main และ shadow positions
กลุ่ม 6 — Pending Orders
CancelAllPendingsByMagic()
ยกเลิก Stop/Limit orders ทั้งหมดของ main magic
CancelAllPendingsByMagicValue(magic)
ยกเลิก orders ของ magic ที่ระบุ
CancelAllManagedPendings()
ยกเลิกทั้ง main และ shadow pending orders
PendingExists(wantType, &ticket, &price)
ตรวจว่า pending order ประเภทที่ต้องการมีอยู่ไหม (main magic) → คืน ticket และ price
PendingExistsByMagic(wantType, magic, &ticket, &price)
เวอร์ชันรับ magic number เพิ่มเติม
8/14
f
ile:///Users/dev/Documents/EA/ZiGZaG/ZigZag_Hedge_2Levels_Fixed_Documentation.html
3/6/26, 9:18 PM
ZigZag Hedge 2 Levels Fixed — เอกสาร Logic
EnsureLotAddShadowPendingAtPrice(type, price)
Sync shadow pending ให้อยู่ที่ราคาที่ต้องการ: 1. ถ้ามี pending อยู่แล้วใกล้ราคา → ปล่อยไว้ 2. ถ้าห่างเกิน 2 points
→ ลบแล้ววางใหม่ 3. ถ้าอยู่ใน Sideway mode → ยกเลิก stop pending ทั้งหมด (counter orders จัดการแทน)
DeleteDuplicatePendings(wantType, keepNewest)
หากมี pending ประเภทเดียวกันซ้ำกัน → เก็บไว้แค่ 1 อัน (ใหม่สุดหรือเก่าสุดตาม parameter)
กลุ่ม 7 — SL/TP
ApplySLTPForOpenedPosition(side, openPrice)
ต
ั
้ง SL และ/หรือ TP ให้ position ที่เพิ่ง fill: - BUY: SL = 
openPrice - SL_pts , TP = 
SELL: SL = 
openPrice + SL_pts , TP = 
openPrice - TP_pts
ท
ำงานเฉพาะเมื่อ 
InpSL_Points > 0 หรือ 
InpTP_Points > 0
openPrice + TP_pts 
กลุ่ม 8 — Lot Progression
GetNextLot_ADD(lastVol)
nextLot = lastVol + InpLotAdd
เช่น
: 0.10 → 0.20 → 0.30 → 0.40 ...
GetNextLot_MUL(lastVol)
nextLot = lastVol × InpLotMultiplier
เช่น
: 0.10 → 0.20 → 0.40 → 0.80 ...
GetNextLot(lastVol)
Dispatch ไปยัง ADD/MUL → apply max lot cap → ถ้าเกิน cap และ 
gPausedByMaxLot = true
InpPauseOnMaxLot = true → ตั้ง
9/14
f
ile:///Users/dev/Documents/EA/ZiGZaG/ZigZag_Hedge_2Levels_Fixed_Documentation.html
3/6/26, 9:18 PM
ZigZag Hedge 2 Levels Fixed — เอกสาร Logic
GetFirstOppLot()
Lot ของ opposite order แรก: - ถ้ามี 
InpFirstOppLot > 0 → ใช้ค่านั้น - MUL mode: 
InpLotMultiplier - ADD mode: 
InpStartLot + InpLotAdd
InpStartLot × 
กลุ่ม 9 — Core Trading Logic
PlaceOppositeStop(lastSide, lots)
วาง pending order ฝั่งตรงข้าม:
lastSide
วาง
BUY
SELL
SELL STOP
BUY STOP
ท
ี
่ราคา
gLowerPrice (หรือ dynamic bid-Step)
gUpperPrice (หรือ dynamic ask+Step)
ตรวจสอบก่อนวาง: - ตลาดต้องอนุญาต trade - ไม่อยู่ใน sideways mode - ไม่ถูก pause by max lot - ลบ pending ซ้ำ
ก
่อน - ถ้ามี pending ถูกประเภทอยู่แล้ว → sync shadow แล้วออก
StartSequence()
เริ่มต้น sequence ใหม่: 1. ตรวจ hedging account 2. ตรวจ trade allowed 3. ตรวจ sideways 4. เรียก
UpdateAbcdSignalIfNeeded() เพื่อหาทิศทาง 5. กำหนด Upper/Lower price จาก ask/bid 6. เปิด BUY หรือ SELL
ท
ี
่ตลาด 7. วาง opposite pending ด้วย 
GetFirstOppLot() 8. ตั้ง 
gStarted = true และ 
MaintainOppositePending()
SaveState()
เรียกทุก tick/timer เพื่อดูแล pending ให้ถูกต้องตลอดเวลา: 1. ถ้า flat → reset sequence 2. ถ้า sideways → ยกเลิก
pending แล้วรอ 3. ถ้า max lot paused → ยกเลิก pending 4. ลบ duplicate pendings 5. ถ้า
InpFollowPriceForPending → reprice ถ้าห่างเกิน threshold 6. ถ้าไม่มี pending ถูกทิศ →
PlaceOppositeStop()
RebuildFromExisting()
สร้าง state กลับหลัง EA restart/reload: 1. นับ positions ที่มีอยู่ 2. หา Upper price จาก BUY position เก่าสุด 3.
ค
ำนวณ Lower = Upper - Step 4. หา 
gLastTriggered และ 
MaintainOppositePending() ถ้าตลาดเปิด
gNextLot จาก position ล่าสุด 5. เรียก
f
ile:///Users/dev/Documents/EA/ZiGZaG/ZigZag_Hedge_2Levels_Fixed_Documentation.html
10/14
3/6/26, 9:18 PM
ZigZag Hedge 2 Levels Fixed — เอกสาร Logic
กลุ่ม 10 — Risk Management
CheckProfitLossCloseAll()
เรียกทุก tick/timer:
Profit Target: - ถ้า 
FloatingProfit >= InpProfitTargetMoney และ 
InpCloseAllOnProfit = true - →
ยกเลิก pendings → ปิด positions ทั้งหมด - ถ้าตลาดปิด: ตั้ง 
gPendingCloseAll = true รอ reopen - ถ้าปิดไม่
หมด: ตั้งธง retry บน timer
Loss Limit: - ถ้า 
FloatingProfit <= InpLossLimitMoney และ 
Profit Target ทุกอย่าง
InpCloseAllOnLoss = true - ทำเหมือน
กลุ่ม 11 — Market Open/Close Detection
HandleMarketOpenClose()
ตรวจสอบทุก tick/timer:
ตลาดปิด: - Print แจ้ง 1 ครั้ง → ตั้ง 
gMarketWasClosed = true → รอ
ตลาดกลับมาเปิด (
gMarketWasClosed เปลี่ยนจาก true → false): 1. ถ้า flat → 
2. ถ้ามี 
ResetSequenceStateIfFlat()
gPendingCloseAll → retry close ทั้งหมด 3. ถ้าไม่มี → rebuild pendings จาก positions ที่มีอยู่
กลุ่ม 12 — Event Handlers
OnInit()
1. 
ตั้ง
 magic + slippage 
สําหรับ
 trade object
2. UpdateAbcdSignalIfNeeded() (best-effort)
3. LoadState() 
จาก
 GlobalVariables
4. ResetSequenceStateIfFlat("OnInit: flat")
5. RebuildFromExisting() 
ถา
 state 
ไม่สมบูรณ์
6. EventSetTimer(InpTimerSeconds)
7. StartSequence() 
ถา
 AutoStart 
และยังไม่
 started
8. MaintainOppositePending() 
ถา
 positions 
มีอยู่
11/14
f
ile:///Users/dev/Documents/EA/ZiGZaG/ZigZag_Hedge_2Levels_Fixed_Documentation.html
3/6/26, 9:18 PM
ZigZag Hedge 2 Levels Fixed — เอกสาร Logic
OnDeinit(reason)
1. SaveState()
2. EventKillTimer()
3. 
ปลอย
 ZigZag handle
4. 
ปลอย
 ATR handle
5. 
ปลอย
 Sideway ATR handle (module)
OnTimer() (รันทุก 
InpTimerSeconds วินาที)
1. HandleMarketOpenClose()
2. ResetSequenceStateIfFlat()
3. UpdateAbcdSignalIfNeeded()
4. ZZH2L_ManageLotAddTrailingStop() → 
ดูแล
 trailing 
ของ
 shadow
5. ZZH2L_MaintainSidewayCounterOrders() → counter orders 
ตอน
 sideways
6. 
ถา
 gPendingCloseAll → retry close
7. MaintainOppositePending()
OnTick() (รันทุก tick)
1. HandleMarketOpenClose()
2. ResetSequenceStateIfFlat()
3. UpdateAbcdSignalIfNeeded()
4. ZZH2L_ManageLotAddTrailingStop()
5. ZZH2L_MaintainSidewayCounterOrders()
6. StartSequence() 
ถา
 AutoStart 
และ
 flat
7. 
ถา
 gPendingCloseAll → return (
รอ
 timer)
8. 
ถา
 MaxCycles 
ครบ
 → 
ยกเลิก
 pending + CheckProfitLoss
9. CheckProfitLossCloseAll()
10. MaintainOppositePending()
12/14
f
ile:///Users/dev/Documents/EA/ZiGZaG/ZigZag_Hedge_2Levels_Fixed_Documentation.html
3/6/26, 9:18 PM
ZigZag Hedge 2 Levels Fixed — เอกสาร Logic
OnTradeTransaction() (รับ deal fill event)
1. 
ตรวจวาเปน
 DEAL_ADD 
ของ
 magic/symbol 
ที่ถูก
2. Guard: 
ถา
 deal 
นี้
 process 
แล้ว
 → 
ออก
3. 
บันทึก
 gLastDealMs (
ใช้
 cooldown)
4. 
อาน
 deal type → 
กําหนด
 gLastTriggered
5. gCycles++
6. ApplySLTPForOpenedPosition()
7. gNextLot = GetNextLot(vol)
8. 
ถา
 MaxCycles 
ครบ
 → 
ยกเลิก
 pending + SaveState + return
9. PlaceOppositeStop(gLastTriggered, gNextLot)
10. SaveState()
Diagram: Sequence การเทรด
ราคา
│
│  Upper Level ────────────────── BUY STOP ──┐
│                                             │ (fill → SELL ↓ + BUY STOP 
วาง
)
│  [
เปด
 BUY 
ตลาด
]
│
│  Lower Level ─── SELL STOP ────────────────┐
│                  (fill → BUY ↑ + SELL STOP 
วาง
)
│
└──────────────────────────────────────────── 
เวลา
Lot progression (ADD mode): 0.10 → 0.20 → 0.30 → ...
Lot progression (MUL mode): 0.10 → 0.20 → 0.40 → 0.80 → ...
13/14
f
ile:///Users/dev/Documents/EA/ZiGZaG/ZigZag_Hedge_2Levels_Fixed_Documentation.html
Shadow / Module ภายนอก (ZZH2L_LotAdd_TrailingModule.mqh)
ฟังก์ชัน หน้าที่
ZZH2L_PlaceLotAddShadowOrder_PendingAtPrice() วาง shadow pending order
ZZH2L_ManageLotAddTrailingStop() ลาก trailing stop สำหรับ shadow positions
ZZH2L_MaintainSidewayCounterOrders() วาง BUY LIMIT/SELL LIMIT เมื่อ ATR ต่ำ (sideway)
ZZH2L_IsSidewayMode() เช็คว่าอยู่ใน sideway mode ไหม
ZZH2L_CancelAllShadowPendings() ยกเลิก shadow pendings ทั้งหมด
ZZH2L_ReleaseSidewayAtrHandle() ปล่อย ATR handle ของ module
Persistence (GlobalVariables)
State ถูกบันทึกใน Terminal GlobalVariables เพื่อ survive การ restart:
Key ค่า
ZZH2LV8_{Symbol}_{Magic}_upper gUpperPrice
ZZH2LV8_{Symbol}_{Magic}_lower gLowerPrice
ZZH2LV8_{Symbol}_{Magic}_nextlot gNextLot
ZZH2LV8_{Symbol}_{Magic}_cycles gCycles
ZZH2LV8_{Symbol}_{Magic}_last gLastTriggered
ZZH2LV8_{Symbol}_{Magic}_started gStarted
ZZH2LV8_{Symbol}_{Magic}_pclose gPendingCloseAl