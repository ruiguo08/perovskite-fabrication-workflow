# Experiment Workflow Guide / 实验全流程操作指南

> Bilingual guide: English first, Chinese below (after the divider).
> 双语指南：先英文，分隔线之后为中文。

---

## Part 1 — English

Step-by-step operating guide from creating a new experiment to uploading
device test data. Interface buttons are given in English (bold); the flow and
validation rules match the current system version.

### Roles and responsibilities

| Role | What it can do |
| --- | --- |
| Student | Create experiment plans, submit for approval, release plans, freeze batches, run fabrication, upload test data |
| Instructor | Approve plans, decide substrate-count exceptions, review the comparison view, cancel batches |
| Administrator | Everything an instructor can, plus base-data maintenance (Campaigns, Device layouts, Materials, Baselines, Users) |

**Before you start (administrator):** make sure at least one active Campaign
and Device layout exist (both are required when a student creates an
experiment); prepare Baselines and Layer presets if the baseline shortcut is
wanted.

### Flow overview

```
Experiment plan (plan_status):
 draft → pending_approval → approved → released → in_progress → completed
   (student saves) (student submits) (instructor approves) (student releases) (student starts fabrication) (student completes fabrication)
                                   └────────────────────────────┴── batches are frozen in this window

Fabrication batch (batch status):
 draft → ready → in_progress → completed
 (frozen)  (Mark ready)  (Start execution)  (Complete batch)
```

Any non-terminal state can be ended with **Cancel plan / Cancel batch**
(cancellation is final).

### Step 1 — Create a new experiment (student)

Sidebar **Experiments** → new experiment opens a five-step wizard:

1. **Starting point**
   - Choose a **Campaign** (required).
   - **Baseline reference** (optional shortcut): selecting a baseline deep-copies
     its complete recipe into an editable draft; leave empty to plan from
     scratch. Either way the experiment stores its own complete snapshot and
     the baseline is provenance only.
2. **Substrate**
   - Fill in substrate material, vendor, type number, width/length (mm).
   - Choose a **Device layout**: it fixes the devices per substrate and the
     active area used later to parse test data.
3. **Layer stack**
   - Add functional layers in fabrication order. Each layer may configure:
     - **Solution**: `weighed_solids` (solids + solvents) or
       `diluted_dispersion` (stock dispersion);
     - **Process**: spin coating + annealing / sputtering / thermal
       evaporation / ALD;
     - the perovskite layer uses **spin coating + VCD** (evacuate/gas-backfill
       stages row by row — see `docs/vcd-program-entry-guide.md`).
4. **Conditions**
   - At least one **control**; each **target** is a complete independent
     snapshot (not an incremental diff against control) — configure its layer
     and process differences explicitly.
   - Each condition picks a device layout and a **planned substrate count**:
     at least 3 by default; below that, request a substrate exception on the
     condition card (a reason is required; an instructor must approve before
     submission).
   - A target without its own complete layer configuration is flagged manual
     review and blocks submission.
5. **Review**
   - Check the summary table (provenance, substrate, layer order, per-condition
     configuration) and save.

After saving the plan status is **draft**; hash-verified recipe snapshots have
been generated for every condition.

### Step 2 — Submit for approval (student)

Experiment detail page → **Plan actions** → **Submit for approval**. The
status becomes `pending_approval` and waits for an instructor.

### Step 3 — Review and approve (instructor / administrator)

Open the experiment detail page:

- The **Condition comparison** table compares all conditions layer by layer in
  device-stack order: differing parameters are highlighted in amber, identical
  layers collapse by default (click to expand every parameter). Each layer
  shows its solution, spin coating, VCD, annealing, and vacuum-deposition
  values. Raw data remains available under **Advanced: raw snapshots (JSON)**.
- After checking, click **Approve plan** → status `approved`.

### Step 4 — Release the plan (student)

Experiment detail page → **Release approved plan** → status `released`.

### Step 5 — Freeze a fabrication batch (student) ⚠️ do not skip

In the **Fabrication batches** section fill in batch notes → **Freeze
fabrication batch**:

- The system freezes every condition snapshot into the batch and **automatically
  generates**: numbered substrates and devices, the solution preparation list
  (identical recipes merged and shared), the process execution list (identical
  processes merged and shared), and the run sheet.
- **This step cannot be skipped**: with zero batches the system refuses to
  start fabrication and no CSV test data can ever be uploaded (a warning banner
  on the page reminds you).
- If fabrication already started (`in_progress`) and the batch was forgotten,
  this form is still available — freeze the batch now.

### Step 6 — Start fabrication (student)

Experiment detail page → **Start fabrication** → status `in_progress`.
Prerequisite: at least one frozen batch.

### Step 7 — Execute the run sheet (student, batch page)

Open the batch code to reach the run sheet page and work top to bottom:

1. **Mark ready** (`draft → ready`): every solution preparation must have at
   least one use and every process execution at least one member (validated by
   the server).
2. **Start execution** (`ready → in_progress`).
3. **Record actual values**. Every solution preparation / process execution has
   an **Actual recording** dropdown:
   - **Recorded as planned** — reality matched the plan; one click (the server
     copies the planned snapshot into the actual record);
   - **Record adjusted parameters** — reality diverged; the editor is
     pre-filled with the planned values, adjust and save;
   - process executions also record an equipment identifier.
   - The top of the page shows `Recorded X/Y preparations · X/Y executions`;
     when everything matched the plan you can press **Record all as planned
     (N)** to confirm every unrecorded item at once (already-adjusted records
     are untouched; safe to click repeatedly).
4. Use **Split / Merge** to reorganize preparations or executions, and the
   **Deviations** section to record departures from plan (solution loss,
   temperature overshoot, …) for the audit trail.

### Step 8 — Complete the batch (student)

Once every solution preparation is `consumed/discarded` and every process
execution is in a terminal state, click **Complete batch**:

- Fill in the **actual substrate count** per condition (pre-filled with the
  planned count; usually a direct confirmation);
- an actual count below planned requires a shortfall reason (recorded as a
  fabrication_shortfall deviation); a count above planned automatically
  materializes the extra substrates/devices;
- confirmation commits status, counts, and deviations in one transaction and
  the batch becomes `completed`.

### Step 9 — Complete fabrication (student)

Back on the experiment detail page → **Complete fabrication** → status
`completed`. Prerequisite: at least one batch (not necessarily completed).

### Step 10 — Upload test data (student)

Experiment detail page, **Characterization results** → **Upload results**:

1. Choose the **Fabrication batch** that produced the devices (only
   `in_progress` or `completed` batches are eligible);
2. choose the J-V CSV file (≤ 10 MB; the same file cannot be uploaded twice —
   the server deduplicates by SHA-256);
3. **Read devices and continue** — the parser extracts each device's
   forward/reverse scans and preliminary metrics;
4. on the result detail page assign every substrate to its condition group
   (control / target …) and save once all are assigned.

Afterwards the **Results** page shows per-device J-V metrics (Voc, Jsc, FF,
PCE, …) and condition comparisons.

### FAQ

- **Cannot click Start fabrication?** No batch exists yet. Freeze one first in
  the Fabrication batches section (available in both `released` and
  `in_progress`).
- **Forgot the batch and fabrication already started?** Not a problem: the
  batch form stays available while `in_progress`; freeze one and continue.
- **Submission complains about manual review?** A target condition lacks its
  own complete layer configuration; go back to wizard step 4 and complete the
  target's layers and process.
- **Fewer than 3 substrates?** Request a substrate exception on the condition
  card and wait for instructor approval.
- **No batch selectable on the upload page?** Only `in_progress` or
  `completed` batches are listed; advance the batch status first.
- **How do CSV devices map to substrates?** The parser groups devices by the
  trace **Name** label (`.Forward` / `.Reverse` suffixes are stripped); each
  device needs a forward and a reverse scan (direction is read from the label
  when present, otherwise inferred from the voltage sweep), then devices are
  assigned to substrates using the batch's substrate-device manifest.

---

## Part 2 — 中文

从创建新实验到上传器件测试数据的完整操作说明。界面上各按钮均以英文标注（加粗部分），流程与系统当前版本的校验规则一致。

### 角色与职责

| 角色 | 可以做的事 |
| --- | --- |
| Student（学生） | 创建实验计划、提交审批、发布计划、冻结批次、执行制造、上传测试数据 |
| Instructor（教师） | 审批计划、审批基底数量例外、审阅对比视图、取消批次 |
| Administrator（管理员） | 拥有教师全部权限，另负责基础数据维护（Campaigns、Device layouts、Materials、Baselines、Users） |

**开始之前（管理员）**：确认已建好至少一个活跃 Campaign 和 Device layout（学生建实验时必选）；如需走基线捷径，再准备 Baseline 与 Layer presets。

### 流程总览

```
实验计划（plan_status）：
 draft → pending_approval → approved → released → in_progress → completed
   (学生保存)   (学生提交)      (教师批准)   (学生发布)    (学生开始制造)   (学生完成制造)
                                    └────────────────────────────┴── 期间冻结批次

制造批次（batch status）：
 draft → ready → in_progress → completed
 (冻结生成)  (Mark ready)  (Start execution)  (Complete batch)
```

任一非终态都可以 **Cancel plan / Cancel batch** 终止（取消不可恢复）。

---

### 第 1 步：创建新实验（学生）

左侧导航 **Experiments** → 新建实验，进入五步向导：

1. **Starting point**
   - 选择 **Campaign**（必填）。
   - **Baseline reference**（可选捷径）：选择基线后系统把完整配方深拷贝为可编辑草稿；留空则从空白开始。无论哪种方式，实验保存的是自己的完整快照，基线仅作来源记录。
2. **Substrate**
   - 填基片材料、供应商、型号、长宽（mm）。
   - 选择 **Device layout**：决定每片基片的器件数量与有效面积（后续测试数据按此解析）。
3. **Layer stack**
   - 按制备顺序添加功能层。每层可配置：
     - **溶液**（Solution）：`weighed_solids`（称固体+溶剂）或 `diluted_dispersion`（分散液稀释）；
     - **工艺**（Process）：旋涂+退火 / 溅射 / 热蒸发 / ALD；
     - 钙钛矿层使用 **spin coating + VCD** 程序（evacuate/背气阶段逐行填写，详见 `docs/vcd-program-entry-guide.md`）。
4. **Conditions**
   - 至少一个 **control** 条件；每个 **target** 是一份完整独立快照（不是对 control 的增量修改），逐一配置其层与工艺差异。
   - 每个条件选择 device layout 与 **planned substrate count**：默认必须 ≥ 3 片；不够时在该条件卡片上申请 substrate exception（填写理由，教师批准后方可提交）。
   - target 若没有完整独立的层配置，系统会标记 manual review 并阻止提交。
5. **Review**
   - 核对汇总表（来源、基片、层序、每条件配置），确认无误后保存。

保存后实验状态为 **draft**，系统已为每个条件生成哈希校验的配方快照。

### 第 2 步：提交审批（学生）

实验详情页 → **Plan actions** → **Submit for approval**。状态变为 `pending_approval`，等待教师。

### 第 3 步：审批计划（教师 / 管理员）

打开实验详情页：

- 顶部 **Condition comparison** 按器件层顺序逐层对比所有条件：差异参数琥珀色高亮，完全相同的层默认折叠（点击可展开查看全部参数）；层内可看到溶液、旋涂、VCD、退火、真空沉积逐项数值。需要原始数据时展开卡片底部 **Advanced: raw snapshots (JSON)**。
- 核对无误后点击 **Approve plan** → 状态 `approved`。

### 第 4 步：发布计划（学生）

实验详情页 → **Release approved plan** → 状态 `released`。

### 第 5 步：冻结制造批次（学生）⚠️ 不要跳过

在实验页 **Fabrication batches** 区域填写批次备注 → **Freeze fabrication batch**：

- 系统把所有条件快照冻结进批次，并**自动生成**：基片与器件编号、溶液配制单（相同配方自动合并共享）、工艺执行单（相同工艺自动合并共享）、run sheet。
- **这一步不可跳过**：一个批次都没有时，系统会拒绝"开始制造"，也无法上传任何 CSV 测试数据（页面顶部有黄色警告条提醒）。
- 如果已经开始制造（`in_progress`）才发现漏建批次，此表单仍然可用，直接补建即可。

### 第 6 步：开始制造（学生）

实验页 → **Start fabrication** → 状态 `in_progress`。前提：至少已冻结一个批次。

### 第 7 步：执行 run sheet（学生，批次页）

点击批次编号进入 run sheet 页面，按顺序推进：

1. **Mark ready**（`draft → ready`）：要求每条溶液配制单至少被一个条件使用、每条工艺执行单至少有一个成员（系统自动校验）。
2. **Start execution**（`ready → in_progress`）。
3. **记录实际参数**。每条溶液配制 / 工艺执行都有 **Actual recording** 下拉：
   - **Recorded as planned** — 实际与计划一致，一键确认（服务端把计划快照复制为实际记录）；
   - **Record adjusted parameters** — 实际有偏差，编辑器已预填计划值，改动后保存；
   - 工艺执行还需填写设备标识（equipment identifier）。
   - 顶部显示进度 `Recorded X/Y preparations · X/Y executions`；确认与计划全部一致时，可点 **Record all as planned (N)** 一键批量确认（已手工调整过的记录不受影响，可重复点击）。
4. 需要拆分/合并配制单或执行单时用对应 **Split / Merge** 操作；实际偏离计划的量（如溶液损耗、短时超温）用 **Deviations** 区记录，留档备查。

### 第 8 步：完成批次（学生）

所有溶液配制单为 `consumed/discarded`、所有工艺执行为终态后，点 **Complete batch**：

- 对话框中为每个条件填写**实际基片数**（已预填计划数，一般为直接确认）；
- 实际 < 计划时必须填写 shortfall 原因（生成 fabrication_shortfall deviation）；实际 > 计划时系统自动补建多余基片/器件记录；
- 确认后一次事务提交，批次 `completed`。

### 第 9 步：完成制造（学生）

回到实验页 → **Complete fabrication** → 状态 `completed`。前提：至少一个批次（不限是否 completed）。

### 第 10 步：上传测试数据（学生）

实验页 **Characterization results** → **Upload results**：

1. 选择产生这批器件的 **Fabrication batch**（仅 `in_progress` 或 `completed` 的批次可选）；
2. 选择 JV 测试 CSV 文件（≤ 10 MB，同一文件不可重复上传，服务端按 SHA-256 去重）；
3. **Read devices and continue** — 系统解析出每个器件的正/反向扫描曲线与初步指标；
4. 在结果详情页把每个基片（substrate）分配到对应的条件组（control / target…），全部分配后保存。

之后可在 **Results** 页查看各器件 J-V 指标（Voc、Jsc、FF、PCE 等）及条件间对比。

### 常见问题

- **点不了 Start fabrication？** 还没有冻结任何批次。回到实验页 Fabrication batches 先 `Freeze fabrication batch`（released 和 in_progress 状态都可以建）。
- **忘了建批次且已经开始制造？** 不影响：批次创建入口在 `in_progress` 仍然开放，补建后继续即可。
- **提交时提示 manual review？** target 条件缺少完整独立的层配置，回向导第 4 步把该 target 的层和工艺补全。
- **基片不够 3 片？** 在该条件卡片申请 substrate exception，等教师批准。
- **CSV 上传后看不到批次可选？** 只有 `in_progress` 或 `completed` 的批次在上传列表；先推进批次状态。
- **CSV 里器件如何对应基片？** 解析器按 trace 的 **Name** 列标签分组器件（自动去掉 `.Forward` / `.Reverse` 后缀），每个器件需包含正向与反向两条扫描曲线（扫描方向优先从标签识别，否则按数据电压走向自动判断），再按批次生成的基片-器件清单做分配。
