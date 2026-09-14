# 班级插班生 LRU 调度算法开发文档

## 1. 概述
本文档描述一个基于 **LRU（Least Recently Used，最近最少使用）** 淘汰策略的“班级插班生”调度模块。该模块用于管理学校内多个班级的学生名单及人数状态。当某班级人数达到上限（45 人）且需要插入新学生时，系统自动识别出该班级中“最近最不经常被老师点名”的学生，并将其调动至其他未满的班级；若所有班级均满员，则自动生成新班级。

本模块对外提供以下核心操作：
- **插入插班生** (`add_student`)：尝试将新生加入指定班级。
- **点名记录** (`record_attendance`)：模拟老师点名操作，将该学生标记为“最近使用”。
- **获取班级列表** (`get_classes`)：获取所有班级的当前状态（人数、未满名额等）。
- **生成新班级** (`create_new_class`)：在系统自动触发的情况下执行。

模块内部采用 **哈希表 + 双向链表**（Python `collections.OrderedDict`）的数据结构，确保所有操作的平均时间复杂度为 O(1)。

## 2. 需求分析

### 2.1 核心业务规则
1.  **班级容量限制**：每个班级最大承载人数为 **45 人**。
2.  **初始状态**：支持初始化多个班级，每个班级当前人数小于等于 45。
3.  **插班生插入流程**：
    -   当向一个班级（Class A）插入插班生时：
        -   若 Class A 当前人数 < 45：直接插入成功。
        -   若 Class A 当前人数 == 45（满员）：
            -   **触发淘汰机制**：查找 Class A 中 LRU 值最大的学生（即最近最长未被点名）。
            -   **执行调动**：将该学生移出 Class A，插入到一个未满的班级（Class B）中。
            -   **递归/迭代处理**：若 Class B 也是满员的，则对 Class B 重复上述淘汰逻辑，直到找到一个未满的班级或触发创建新班级。
4.  **新班级生成规则**：如果所有现有班级均已满员且需要接收调动来的学生，系统自动创建一个初始人数为 0 的新班级，并将该学生放入其中。
5.  **点名状态更新**：任何一次成功的点名操作（无论是通过接口调用还是内部淘汰逻辑），都必须将该学生在当前班级中的 LRU 优先级提升（标记为“最近使用”）。

### 2.2 非功能需求
-   **时间复杂度**：插入、访问、点名、查找淘汰对象的操作平均需在 O(1) 时间内完成。
-   **空间复杂度**：额外空间开销与总学生数成线性关系。
-   **数据一致性**：保证在多线程或高频调用下，LRU 链表的顺序与哈希表映射保持一致。

## 3. 功能设计

### 3.1 实体模型
系统主要由两类对象组成：
1.  **Student (学生)**：代表一个插班生。具有唯一标识符（ID）、姓名、所属班级 ID 等属性。在 LRU 结构中作为“键”或“值”存在。
2.  **ClassNode (班级节点)**：维护一个班级的 LRU 缓存结构。包含容量上限（45）和具体的 LRU 实现对象。

### 3.2 调度策略
采用 **LRU Cache** 作为核心数据结构的变体应用：
-   **Key**: 学生的唯一 ID。
-   **Value**: 学生详细信息对象。
-   **Access Order**: 双向链表维护点的最近使用顺序。
    -   **Head (最近)**: 刚被点名或刚插入的学生。
    -   **Tail (最远)**: 需要被淘汰的候选人。

### 3.3 状态机设计
系统状态流转：
-   `Insert Student`: 
    -   Check Target Class Size < 45? -> Yes: Insert Success.
    -   No (Target Full): Identify LRU Candidate -> Remove from Target -> Find Next Empty Class (Iterative Search).
-   `Find Next Empty Class`:
    -   Iterate through all classes.
    -   If Found Empty Class: Move Student Here -> End.
    -   If All Full & New Student Needed: Create New Class (Empty) -> Insert Here -> End.

## 4. 技术方案

### 4.1 数据结构选择
借鉴现有 `LRU_python_way.py` 的实现方式，利用 Python 标准库 `collections.OrderedDict` 模拟哈希表 + 双向链表。
-   **OrderedDict**: 内部维护了键的插入顺序和最近访问顺序。
    -   `popitem(last=False)`: 移除并返回最久未使用的项（Tail）。
    -   `__setitem__` (或 `move_to_end`): 将某学生标记为最近使用（Move to Head），同时更新哈希映射。
-   **辅助字典**: 用于快速查找某个学生当前所在的班级，以便在淘汰时将其从原班级移除并插入目标班级。

### 4.2 模块划分
-   `StudentManager`: 全局管理器，维护所有班级的列表，处理“跨班级调动”的逻辑（递归/迭代）。
-   `ClassLRUCache`: 继承或封装现有的 `LRUCache` 类，增加班级特有的属性（如当前人数、班级名称）。

### 4.3 核心算法流程 (Python 伪代码)
```python
def insert_student(student, target_class_id):
    # 1. 定位目标班级
    target_class = get_class_by_id(target_class_id)
    
    # 2. 检查容量
    if len(target_class) < MAX_CAPACITY:
        # 未满，直接插入并标记为最近使用
        target_class.cache.put(student.id, student.data)
        return SUCCESS
    
    # 3. 满员情况：需要淘汰并迁移
    evicted_student = target_class.cache.popitem(last=False) # 获取 LRU (Tail)
    
    # 4. 递归/迭代寻找接收方班级
    current_holder = target_class
    while True:
        # 检查当前持有者是否已满
        if len(current_holder) < MAX_CAPACITY:
            current_holder.cache.put(evicted_student.id, evicted_student.data)
            break
        
        # 若仍不满 (例如是新空班)，或者就是当前目标，则继续寻找或创建
        # 注意：如果 target_class 满了，我们需要把 evicted_student 放入别的班级
        # 逻辑修正：我们要找到的是能接收 evicted_student 的班级。
        # 如果所有班都满，则创建一个新班。
        
        if current_holder == target_class:
             # 这是一个特殊的死循环风险点，需明确：
             # 实际上，我们是把 person X 从 A 拿出，放入 B。
             # 如果 B 满了，B 也要拿出 Y。Y 需要放入 C...
             # 最终一定会遇到一个不满的班级或创建新班。
             pass
        
        # 寻找其他未满班级
        next_class = find_or_create_empty_class()
        
        if next_class:
            current_holder.cache.put(evicted_student.id, evicted_student.data) 
            break # 错误，上面逻辑有误，重新梳理
            
    # 修正后的逻辑：
    # 1. 从 target 移除 evicted
    # 2. 寻找所有班级中未满的。
    # 3. 如果找到未满的 class B: put(evicted, classB)
    # 4. 如果没有 (全满): 
    #    a. 创建一个新班级 NewC (空)
    #    b. put(evicted, NewC)
```

## 5. 接口设计

### 5.1 主要接口

| 接口名称 | 方法签名 | 参数说明 | 返回值 | 描述 |
| :--- | :--- | :--- | :--- | :--- |
| **初始化** | `initialize(classes_config)` | `classes_config`: dict，键为班级 ID，值为初始学生列表或空列表 | `Manager` 实例 | 初始化系统，加载现有班级及学生数据。 |
| **插入插班生** | `add_transfer_student(class_id, student_obj)` | `class_id`: 目标班级 ID<br>`student_obj`: 新生对象 | `bool`/`Student` | 尝试将插班生加入指定班级。若原班级满，则自动进行调动。返回操作结果及最终停留的班级 ID。 |
| **点名记录** | `record_attendance(class_id, student_id)` | `class_id`: 班级 ID<br>`student_id`: 学生 ID | `bool` | 标记该学生为最近使用（移动到 LRU Head）。若学生不存在或不在该班级，返回 False。 |
| **获取状态** | `get_class_status()` | - | `dict` | 返回所有班级的当前人数及未满名额信息。 |
| **创建新班** | `force_create_new_class()` | - | `bool` | 手动触发创建空班级（仅在需要时内部自动触发）。 |

## 6. 数据结构定义

### 6.1 学生对象 (Student)
```python
class Student:
    def __init__(self, student_id, name):
        self.id = student_id          # Unique ID，作为 LRU Cache 的 Key
        self.name = name              # 存储信息
        # 在 Cache 中，value 即为 Student 对象本身或包含该对象的字典
```

### 6.2 班级缓存结构 (ClassCache)
基于 `OrderedDict`。
-   **Key**: `student_id` (int/str)
-   **Value**: `Student` object
-   **Order**: 插入或访问的顺序（越靠右/最后插入的越“热”，最靠左的越“冷”）。

### 6.3 班级管理器状态
-   `classes`: `dict[class_id -> ClassCache]`
-   `max_capacity`: `int` (固定为 45)
-   `next_class_count`: `int` (当前存在的班级总数，用于生成新班级 ID)

## 7. 测试计划

### 7.1 单元测试用例

#### 场景 1：正常插入未满班级
-   **输入**: 班级 A 有 40 人，插入学生 S_new。
-   **预期**: S_new 直接加入 A，A 变为 41 人，S_new 为 LRU Head。

#### 场景 2：满员班级触发淘汰（单次调动）
-   **输入**: 
    -   班级 A (45/45): [S1...S45]
    -   班级 B (40/45)
    -   插入 S_new 到 A。
-   **操作**: `add_transfer_student(A, S_new)` -> `record_attendance(A, S1)` ... `record_attendance(A, S45)` (模拟近期活跃)。假设 S2 是 LRU (Tail)。
-   **预期**: 
    1. 从 A 移除 S2。
    2. 将 S2 加入 B。
    3. B 变为 41 人，S2 变为 B 的 LRU Head。
    4. 返回成功及 S2 最终班级为 B。

#### 场景 3：连环淘汰（链式反应）
-   **输入**: 
    -   A, B, C 均为满员 (45/45)。
    -   插入 S_new 到 A。
-   **操作**: `add_transfer_student(A, S_new)`。
-   **预期**:
    1. A 淘汰 LRU_S2 -> 移至 B。B 已满，触发 B 的淘汰逻辑。
    2. B 淘汰其当前的 LRU (可能是刚移入的 S2 或其他) -> 移至 C。C 已满，触发 C 的淘汰逻辑。
    3. C 淘汰其当前 LRU -> 创建新班级 D (0/45)。
    4. 放入 D。
-   **结果**: S_new 进入 A，S_old 经过 A->B->C->D 的路径最终稳定在 D。

#### 场景 4：点名更新 LRU 顺序
-   **输入**: 班级 A 有 S1...S45。
-   **操作**: `record_attendance(A, S20)`。
-   **预期**: S20 从链表中被移到头部（Head），下次淘汰将优先选择除 S20 外最近未点名的学生。

### 7.2 边界测试
-   **初始空班级**: 初始化时所有班级均为空，插入第一个插班生是否正常。
-   **全满状态**: 4 个班级均为 45 人，此时插入操作必须成功创建第 5 个班级。
-   **容量为 0**: (可选) 如果允许配置为 0，需处理异常；但需求固定为<=45，故不做此测试。

## 8. 其他注意事项

1.  **并发安全**：现有 `OrderedDict` 实现非线程安全。若在多线程环境下使用（如多服务器节点模拟），需在类外部封装全局锁（`threading.Lock`）或引入 `queue.Queue` 等线程安全结构。本项目暂假设单进程运行，未加锁。
2.  **数据持久化**：当前文档仅关注内存中的 LRU 逻辑。若需将班级状态保存至数据库，需在 `ClassCache` 中增加 `sync_to_db()` 方法，并在每次淘汰或创建新班级时同步。
3.  **学生身份校验**：在插入插班生前，建议校验 `student_id` 是否已存在于系统中（防止重复生成 ID），若存在则视为更新其位置或直接覆盖逻辑（需求未明确说明，通常插班生应为新 ID）。
4.  **性能优化**：当班级数量极大时，查找“未满班级”的过程如果是遍历所有班级列表 `O(N)`，在极端情况下可能成为瓶颈。如果班级数量动态增长且很大，建议维护一个 `set` 或 `双向链表` 来管理所有未满的班级索引，实现 O(1) 查找。对于当前需求（4 个班级），线性扫描完全可接受。

## 9. 代码规格映射检查
本文档已明确：
-   [x] LRU 淘汰策略的具体应用场景（班级人数满员）。
-   [x] “最近使用”的定义（老师点名操作）。
-   [x] 跨班级调动的递归/迭代逻辑。
-   [x] 新班级创建的触发条件。
-   [x] 基于 Python `OrderedDict` 的实现方案。

开发者可依据本文档直接生成 `ClassLRUCache` 和 `StudentManager` 类代码，无需回溯原始需求文档。