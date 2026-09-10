# 班级插班生 LRU 调度算法开发文档

## 1. 概述
本文档描述一个基于 **LRU（Least Recently Used，最近最少使用）** 淘汰策略的“班级人数动态平衡”模块。该模块模拟学校管理场景：在四个初始状态不同的班级中插入新学生（插班生），当某班级人数达到上限（45人）时，自动将该班级内**最久未被点名记录**的学生迁移至未满员的其他班级；若所有班级均满员且仍有新生入校，则自动创建新班级。

本模块是现有数字存储 LRU 缓存算法在特定业务场景下的泛化应用。它将“数字”映射为“学生”，将“最近使用/修改次数”映射为“被老师点名频率”。系统需要维护每个学生的姓名、当前所在班级以及最后一次被点名的时间戳，以确保能准确识别并迁移最久未使用的学生。

## 2. 需求分析
### 2.1 业务规则与约束
- **初始状态**：学校现有四个班级（Class A, B, C, D），每个班级的当前人数不同且均 $\le 45$。
- **容量限制**：单个班级最大容量为 $K=45$ 人。
- **插班生处理流程**：
    1. 新学期插入一名新学生（记为 `NewStudent`）。
    2. 遍历所有未满员的目标班级，尝试插入。
    3. **冲突解决（核心逻辑）**：当目标班级已满（$Count = 45$）且无法直接插入时，触发 LRU 淘汰机制。
       - 查找该目标班级中**最近最少使用次数最低**的学生。
       - “使用”定义为：学生被老师点名记录的次数累计值 + 更新时间戳辅助排序。若仅靠计数存在平局，优先选择时间最早者（或根据文档扩展性预留字段）。
       - 将该“最久未使用”学生从满员班级移除（设为 `PendingMove`），并插入到目标未满班中。如果原移出班级仍有人数上限限制且因该生离开而释放了一个名额，新进来的插班生直接填补；若需将迁移出的学生安置到其他未满班级，则需在逻辑上增加“二次匹配”或默认将其暂存（*注：根据需求描述“放到其他没有满 45 人的班级”，本实现采用简化策略：优先填充接收方，若存在多目标竞争该生情况下的特殊处理见技术方案；若无明确指定哪个未满班接收，则按轮询逻辑放入第一个未满的班或默认接收方*）。
       - *修正理解*：需求描述为“当一个班级现有人数满了的时候就把这个班级中最近最不经常被老师点到名的学生放到其他没有满 45 人的班级中”。这意味着**触发点是在插入失败时**。此时，源班级（已满）需释放一人给接收方。逻辑链条是：**新同学进入 -> 发现某班满员 -> 从该班踢出一个老弱病残（久未被点名者）-> 将该学生放入另一个未满的班（或直接让出新位）。**
- **溢出处理**：若经过 LRU 淘汰操作后，接收方班级仍已满或全校所有现有班级均无法接纳（即满员状态），则创建一个新的班级 ID（如 Class E, F...）将新学生及被踢出的老生安置进去。

### 2.2 非功能需求
- **实时性**：点名和插班操作需即时反映在缓存中，保证“最近使用”属性的准确性。
- **一致性**：确保同一时间戳下的数据顺序正确（若存在多个学生久未使用）。
- **扩展性**：数据结构应支持存储更多信息字段（如学号、姓名），而不仅仅是数字 ID。

## 3. 功能设计
### 3.1 核心实体定义
系统需维护两类对象：
1.  **Student (学生)**:
    - `id`: 唯一标识符 (int/str)。
    - `name`: 学生姓名 (str)。
    - `count`: 累计被点名次数 (int, >=0)。
    - `last_access_time`: 最后一次访问（被点名）的时间戳 (float/unix_timestamp),用于打破平局。
2.  **ClassManager (班级管理器)**:
    - `class_id`: 班级编号 ("A", "B"... 或 int)。
    - `capacity_limit`: 容量上限 (固定为 45)。
    - `students_map`: 存储该班级学生的映射表，Key为学生ID/对象引用。
    - *内部结构*：为了支持 LRU 逻辑，`ClassManager` 不能仅用 Python 的普通 Dict（无序），必须基于 **OrderedDict** 或自定义链表来维护“最近被点名”的顺序。

### 3.2 核心流程设计 (插班生插入 `add_student`)
输入：学生对象 `student_new`, 目标班级集合 `all_classes`。
逻辑步骤：
1. 检查是否所有班级均满员 (`len(c) == 45 for all c in classes`)。
    - **是**：创建新班级，直接插入成功。返回操作结果（包含新生及被置换出的学生信息）。
    - **否**：进入流程 2。

2. 寻找接收方与受害者 (Victim Selection)：
   - 遍历所有未满的班级 `TargetClass` (排除当前正在处理的源班级)。如果有多个候选，策略需明确（文档暂定：**首选第一个未满的非源班级**）。
   - 检查插入目标班是否已满？
     - **情况 A：目标班未满**。直接插入成功。*注：需求隐含“当一个班级满了...把学生放到其他没满的”。如果接收方也不满，逻辑很简单。若接收方也满但全校只此一处不满（矛盾），则需回溯。简化模型假设总能找到至少一个未满位置或创建新班。*
     - **情况 B：目标班已满** (此时意味着“所有班级都满了”，回到步骤 1)。

   *重新梳理逻辑以符合需求描述细节*："当一个班级现有人数满的时候..."暗示这是一个阻塞点。
   更合理的场景假设是：**插班生进入某具体班组尝试**。如果该班组满，则触发 LRU。
   
   **修正后的精准流程**：
   1. 接收者指定了想要插入的学生（或随机分配）。或者系统自动寻找未满班级？需求未明确分配策略，通常默认为“均匀分布”或“空闲优先”。此处假设为：**将新学生尝试放入第一个未满的班；若该班已满，则触发 LRU**。
   2. **触发条件**：当前候选接收班 `CurrentClass` 人数 = 45。
   3. **LRU 查询**：在 `CurrentClass` 中查找 `count == min(counts)` 且 `last_access_time <= others` (最早) 的学生作为受害者。
   4. **执行迁移**：将该学生从 `CurrentClass` 移除，加入 `PendingTransferList`（或其他未满的班级列表）。由于需求说“放到其他没有满...的”，若此时全校只剩一个不满且已被选中为接收方？这会导致死锁或逻辑复杂。
   *工程化简化假设*：我们维护一个全局学生池或直接操作。当某班已满需腾位置时，踢出的人去填补哪里？需求说“放到其他没有满...的”。如果此时没有其他未满班级（即全校都满了），则直接开新班。如果有多个未满，**默认策略**是放入系统指定的接收方或轮询第一个可用的。
   
   **最终确定逻辑**：
   - 操作 `add_student(s)`。
   - 遍历所有班级找到第一个 `len < 45` 的班级作为 `Target`。
   - 如果找不到（全校满员）且无法腾位置 -> 创建新班，插入成功。
   - 如果在填入 `Target` 时发现其已满？-> 此时说明“找不到未满班级”，应直接开新班。**逻辑矛盾修正**：通常 LRU 发生在写入失败的缓存上。在这里，场景是：**想把人放进 A 班 (已占满)，所以必须从 A 踢出一个人放到 B 班**。如果 B 也满了呢？那就继续找 C...直到找到未满的 D，或者全校都满则建 E。**但是**需求说“把一个班的踢出的学生放到其他没满的”。这意味着我们需要先确定接收者。
   - **折衷方案（符合直觉）**：系统试图将新学生安置到某个班级。若某班已满且必须被插入（例如按顺序或负载均衡），则该班触发 LRU 弹出旧生，该旧生去另一个未满的班。**如果找不到其他未满的班**（意味着全校除了目标班都满了？或者全局只此一处不满但无法接收？）-> **实际上需求描述“当一个班级...满的时候..."是事件驱动**。
   
   *为保持代码简洁且符合常规 LRU 缓存逻辑，本实现采用以下策略*：
   - 维护一个 `LRUCache` 实例对应每个班级。
   - `add_student(student, target_class_id)` (若未指定则自动选择未满最多的或第一个)。
   - **核心冲突解决**：当目标类满时，查找 LRU Victim -> Remove from Target Class -> Insert to *First Available Non-Full* Class. 
     - 如果移除后原班级不满（有空位），新学生直接进。
     - 如果移除的学生去的地方也满了怎么办？需求未定义此极端多退一进的复杂性。**本实现在文档中定义为**：踢出的人直接进入“首个未满”的队列；若该学生被移动导致其所属源班级不再满员，则操作结束。对于接收方是否已满的问题，我们将采用“轮询查找首个非源且非目标未满班级”的策略来处理旧生的安置。

## 4. 技术方案
### 4.1 数据结构选型
沿用提供的 `LRUCache` Python 实现思路（基于 `OrderedDict`），因其内部实现了双向链表特性（通过 `.popitem(last=False)`）：
- **每个班级的存储结构**：使用自定义的 `ClassCache` (继承或模仿 `LRUCache`)。
  - Key: 学生 ID (`student_id`).
  - Value: 包含所有属性的 Student Object.
- **全局班级列表**：字典 `{class_name: ClassCache}`，便于遍历查找未满班级及创建新类。

### 4.2 LRU 逻辑映射
- `make_recently` -> `_move_to_head` (使用 Python dict reassign key trick)。
- `popitem(last=False)` -> **淘汰最久未使用的学生**。该函数会自动删除字典中最早插入（即最久未被更新/访问）的键值对，完美契合需求。

### 4.3 算法流程伪代码
```python
def process_new_student(student, classes_dict):
    # 1. 尝试直接插入逻辑（可选：先找未满班，若没有则看是否需要腾挪）
    full_classes = [c for c in classes_dict.values() if len(c) == ClassLimit]
    
    if not any(classes_dict[c].capacity >= student.count + ...): 
        # 简化版策略
        
    target_cache = select_target_class_for_new_student(student, classes_dict)

    while True:
        cache = target_cache
        current_len = len(cache.cache)
        
        if current_len < ClassLimit:
            # 目标未满，直接插入成功
            student_obj.update_info() 
            cache.put(student.id, student_obj)
            return success_log
        
        else:
            # 2. LRU 淘汰逻辑：从当前已满的 target_cache 中取出受害者
            victim_student = pop_lru_victim(cache.cache) 
            
            if not any_class_available_for_transfer(victim_student): 
               # 如果没有其他未满班级接收该victim（全校满员）
               create_new_class()
               insert_both(student, new_classes[last_added])
               
            else:
                # 3. 转移受害者到另一个未满的班
                available_cache = find_first_non_full_not_source(available_cache_list) 
                if not found and victim == target_student? NO, we have distinct student.
                
                # 注意：这里有一个并发逻辑问题，如果victim去了别的班，原班级空出了一个坑。
                # 新学生现在可以直接进原班级了（因为人数 <45）
                insert_both(student, current_cache) 
                return success_log
                
    if no more classes and still full -> New Class creation handled.
```

## 5. 接口设计 (API)

### 5.1 类定义：`ClassSchedulerManager`
**主要方法：**

| 方法名 | 输入参数 | 返回值 | 描述 |
| :--- | :--- | :--- | :--- |
| `add_student(name, age)` | Student Name (str), Age (int) | Dict/Side-effect | 添加新插班生。若触发 LRU，会自动将老学生迁移并记录日志。<br>返回字典：`{'status': 'success'|'created', 'new_class_id': ..., 'displaced_students': [...]}` |
| `get_student(id)` | Student ID (int) | Student Object / None | 根据唯一 ID 查询任意班级中的指定学生信息。若存在，自动更新其 LRU “最近访问”状态（模拟点名）。 |
| `query_class(class_id)` | Class ID (str/int) | List[Student] | 获取特定班级的所有学生列表及统计信息。<br>返回包含：`count`, `min_lru_score_student_name`. |

### 5.2 Student Object Schema
用于在 Cache Value 中存储的完整对象结构。

```python
class Student:
    def __init__(self, sid):
        self.id = sid           # int: Unique ID (Primary Key)
        self.name = ""          # str 
        self.score_accumulated = 0 # float/int: Sum of points/points given by teachers (proxy for usage frequency? NO. Requirement says "Least recently called". So we need a counter or timestamp).
                                # Correction: The doc needs to track "Frequency" OR just "Last time". Usually LRU is based on Time. 
                                # If requirement implies "least frequent", it's LFU. But algorithm is specified as LRU ("most long not used"). 
                                # So we map "Called by teacher" = Access Event.
        self.last_called_time = 0.0 # float: Unix timestamp of last access (call). Used for tie-breaking or if count isn't the primary metric. 
```

## 6. 数据结构详解 (映射自文档提供的 LRU Python Way)

我们复用 `collections.OrderedDict` 的特性。
对于每个班级：
- **存储结构**：`OrderedDict[StudentID, Student]`.
- **访问逻辑 (`access_student`)**: 
  ```python
  # Pseudo-code for "Teacher called a student" (updates usage)
  if student in cache.cache:
      val = cache.cache.pop(student.id) 
      self.make_recently(val.key) -> puts it at the end of insertion order logic? 
                                            Wait, OrderedDict pops last=False gets oldest. 
                                            To mark as used recently to keep them safe from eviction, we should move it to LRU position (Newest).
      
      # In standard LRU implementation provided:
      self.make_recently(key) -> pop and re-insert at the end? No, usually front or back depends on impl.
  ```
  
- **驱逐逻辑 (`evict`)**: 
  `cache.popitem(last=False)` returns (key_of_oldest_student). This matches "Least Recently Used".

## 7. 测试计划

### 7.1 单元测试场景 (Unit Tests)
使用 Python `unittest` 或 `pytest`。

#### Case A: 基础 LRU 行为验证
- **Setup**: 4 个班级，容量均为 5（用于简化测试）。
- **Action**: 
  - ClassA fill up to capacity.
  - Insert new student X to ClassB (full).
  - Trigger eviction in ClassA? Or insert into B triggers A's LRU if we enforce strict placement rules defined above? 
  - Test: `add_student` when all classes are full but one is target -> verify victim selected correctly by timestamp.
- **Expected**: New student enters, oldest from Target moves to another non-full class (or new class).

#### Case B: 边界条件测试
1. **全员满员**：当 ClassA/B/C/D 均为 45/45，插入新学生。验证是否成功创建 `ClassE`。
2. **空班存在**：有一个班只有 0 人。将旧生迁移至此处，再插入新生。验证逻辑不崩溃且能正确找到“未满”班级接收迁移者。
3. **平局处理**（Tie-Breaker）：构建两个学生久未被点名且时间戳相同的场景（理论上不可能同时发生除非并行写入），或者构造时间极短差值测试稳定性。

#### Case C: 接口调用测试
- `get_student` after eviction: Verify old student is in the *new* location (or new class) but lost from original.
- **Concurrency Check** (Optional): Run multi-threaded insertion to ensure no deadlock on dictionary operations (since standard dict + OrderedDict are not thread-safe for concurrent modify/read, need lock wrapping).

### 7.2 测试数据准备
```python
# Mock Students Generation
import random
def generate_students(count=50): 
    return [{'id': i, 'name': f"Student_{i}", 'last_called': time.time()} for i in range(count)]
```

## 8. 其他注意事项与扩展性说明

1. **关于 LRU vs LFU**: 
   - 用户需求明确提到“最近最不经常...”，这通常暗示基于频率。但算法名称限定为**LRU**。
   - 若仅记录 `last_called_time`，则退化为纯时间基的 LRU。这在工程上更可行且符合文档示例代码逻辑（OrderedDict 顺序）。
   - **注意**：如果“点名”是高频事件而不仅仅是标记访问，单纯用 OrderedDict 顺序可能不足以保证“最不经常使用”被选中，因为一个学生可能被叫过无数次但很久以前最后一次被叫。严格来说 LRU 基于 `last_access` 而非 `total_count`。若需 LFU-LRU 混合策略，需在 Value 中增加计数器并自定义比较逻辑。**本实现文档坚持严格按照用户指定的“LRU算法”，即以最近一次访问时间为准**。

2. **线程安全扩展**：
   - Python 的内置字典操作 (`pop`, `setitem`) 在 CPython GIL 下是原子的，但在复杂循环中不安全。建议为每个班级对象添加 `_threading.Lock`，封装所有读写方法（如 `_lock.acquire() ... release()`）。

3. **性能考量**：
   - OrderedDict 的插入和查找均为 O(1)，符合大规模学生数据的实时需求。创建新班级的操作涉及列表追加或字典新增，复杂度可接受。

4. **配置文件集成**: 
   - 类加载时可从 `config.conf` 读取全局参数（如班级容量上限、日志级别），无需硬编码 45 人限制，便于调整规则。