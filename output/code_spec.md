# 项目技术规格说明书：班级插班生 LRU 调度系统 (ClassScheduler)

## 1. 项目背景与目标
本项目旨在构建一个基于 **LRU（最近最少使用）** 淘汰策略的班级管理系统模块，用于处理新学生（插班生）插入及满员班级的动态平衡。系统将模拟学校场景：当某班级人数达到上限时，自动识别并迁移该班级内“最久未被点名”的学生至其他未满班级或新建班级。

**核心目标：**
- 实现高效的学生状态维护与班级管理。
- 利用 LRU 逻辑（基于时间戳的最近访问时间）解决空间溢出问题。
- 确保数据的一致性、实时性及高并发下的线程安全。

## 2. 技术约束与环境
- **编程语言**: Python 3.x (兼容 CPython)。
- **核心依赖标准库**: `collections.OrderedDict` (利用其 O(1) 的插入/删除特性及 FIFO 语义模拟双向链表), `threading`, `time`.
- **禁止使用外部重型框架**：为保持轻量级和快速集成，本实现不依赖 SQLAlchemy、Django ORM 或 Redis。所有数据结构将在内存中管理（符合 LRU 缓存的原生设计）。
- **编码规范**: PEP8, Type Hinting (using `typing`), Docstrings.

## 3. 现有代码结构概述 (基准)
本系统将基于标准的 Python OOP 范式构建，不依赖外部文件中的具体实现细节（除非明确复用），但逻辑需严格对齐以下抽象模型：
- **存储层**: 使用 `OrderedDict` 作为底层数据结构维护学生集合。Key 为学生 ID，Value 为包含详细信息的字典或对象。
    - *注意*: Python 标准库中已弃用内置的 `dict.get()` O(n) (在有序性依赖下)，应优先使用 `.pop(key, default)` + `__setitem__` 进行访问更新以保证顺序正确（如果业务逻辑要求移动键到末尾）。但考虑到现代 Py3.7+ dict 保持插入序，我们将利用字典直接操作。
- **管理层**: `ClassCache` (单班级实例) -> `SchedulerManager` (全局调度器)。

## 4. 需要新增/修改的文件列表及功能描述

### File: `models.py` (实体定义)
**功能**: 定义学生数据结构和辅助函数，确保类型一致性。
- **类 `StudentData`**:
    - `_id`: int (Primary Key).
    - `_name`: str.
    - `_last_called_time`: float/float (Unix timestamp, default current time on init if not specified? Requirement says "usage" is defined by this field. If new student enters without specific history, treat as 'recently used' upon entry or use 0 for strictly old logic). *Decision*: New students get `time.time()` immediately so they are safe from eviction unless forced in the same tick (unlikely) or if we track total frequency. Based on strict LRU doc: **Last Access Time is key**.
    - `_total_calls`: int = 0 (Optional field for LFU extension, but current spec relies mostly on timestamp. We will include it as metadata).

### File: `cache_engine.py` (班级缓存逻辑)
**功能**: 封装单个班级的 LRU 操作。
- **类 `ClassCacheManager`**:
    - `_capacity`: int = 45.
    - `_students`: OrderedDict[StudentID, StudentData]. Key is the student ID. 
        *Wait*: In standard LRUCache implementation using simple dict: accessing a key updates its position? Python's built-in dict preserves insertion order but `pop(key)` followed by re-insertion (`__setitem__`) makes it 'recent'.
    - **Method `_move_to_head(student_id)`:** 
        ```python
        val = self._students.pop(student_id, None)
        if val: self._students[val['id']] = val # Re-inserts at the END (Most Recently Used position).
        ```
- **Method `get_student(id)`**: Returns student data OR raises KeyError. Triggers `_move_to_head` logic conceptually or explicitly called by caller? 
    - *Spec*: "Querying updates usage". Yes, calling get should update LRU status. So inside ClassManager:
      ```python
      def access(self, key): self._students[key] = self._pop_if_exists(key) # Re-insert to end.
      ```
- **Method `_evict()`:** Calls `self._students.popitem(last=False)` (returns oldest item). Returns the removed student data.

### File: `scheduler.py` (核心调度器)
**功能**: 维护全局班级列表，处理插班逻辑。
- **类 `ClassSchedulerManager`**:
    - `_classes`: dict[str, ClassCacheManager] mapping "A", "B"... to instances.
    - `_lock`: Threading.RLock() for concurrency safety on the global map (optional but recommended per constraints).
    
    **Method `add_student(student_data) -> Dict[Result]`**:
    1. Find first non-full class (`target_class`). If none exists globally, create new empty class ID ("E"). 
       *Correction based on spec*: "When a class is FULL... trigger LRU". This implies we might target a specific one or iterate to find where it fits.
       **Logic refinement**: Iterate through all classes (A-Z).
         - If `len < 45`: Insert here directly. Done.
         - If ALL are full: Create new class, insert there. Done.
       
    *Wait, Re-reading "Trigger Condition"*: The spec says "When a target class is FULL -> trigger LRU". 
    Scenario: System has classes A-D. New student comes in. We try to put them somewhere. If we pick Class A (which happens to be full), we MUST evict from A first before inserting the new one? Or do we just find *any* non-full spot?
    
    **Final Logic Specification for Implementation**:
    - Iterate through existing classes list `all_classes`.
    - Find candidate class: If there are `<45` slots, pick that. 
      - But if ALL current classes (A-D) have 45 people -> Create New Class E, insert new student and the evicted one? No, we don't evict from empty ones unless full.
      
    **Correct LRU Flow Implementation**:
    The spec says: "If target class is FULL... trigger LRU". 
    This implies a scenario where we *want* to fill it or just generally manage space. Let's assume the strategy is **"Insert into first available non-full"**. If that doesn't exist (all full), create new one.
    
    **However**, there is a constraint: "Put evicted student in other < 45 class". 
    Algorithm:
    1. Find `Target` = First class with `len < capacity`.
       - *Case A*: If `Target == None` (All full): Create New Class E, Insert New Student there (and stop).
       - *Case B*: If `Target != None`: 
         - We need to place the new student. But does it displace anyone? Usually no. Just add to Target.
         
    **WAIT! REREADING SPEC LOGIC**: "When a class is FULL, trigger LRU". This implies we might be trying to insert into a full class specifically (e.g., round-robin). 
    *Alternative Strategy*: We iterate classes A->D. If Class A has space -> add there and stop.
    If ALL are full -> Create New.
    
    **Let's stick to the simplest interpretation of "Balancing"**: Try every non-full class until one fits? No, that's inefficient. 
    *Better*: Maintain a list `classes`. When adding:
       - Filter classes where `len < 45`. Sort them by available space (FIFO or random)? Spec says "Round robin logic if needed". Let's assume simple insertion into the first found non-full class works unless specific filling order is required. 
    **BUT**: If Class A has 0 students and D has 1 student, where does new guy go? To keep balance, maybe to A (emptiest)? Or just First Available?
    *Spec Decision*: Insert into **First Non-Full** encountered in iteration list `['A', 'B', ...]`. 
       - If that logic results in the "Full Class" scenario mentioned: Maybe we assume classes are balanced and generally have space, OR if full -> evict.
    
    Let's simplify for code generation robustness:
    **Method**: Iterate all registered class IDs (A,B,C...). Find first where `len < 45`. 
       - If found: Insert New Student there. Done.
       - If not found (All Full): Create Class E, insert there. Done.
    
    *What about the evicted student logic?* "When a target class is full... move oldest to other non-full". 
    This implies we might need to fill a specific slot or balance load? No, it says "If Target Class A (where you want him) IS FULL -> Evict from A, Move Victim to B/C/D (if free), Insert New Guy to A."
    
    **Implementation**: 
       ```python
       target_class_id = next((c for c in class_order if len(cache[c]) < CAPACITY), None)
       if not target_class_id: # All full
           create_new("E") -> insert new. return success(new).
           
       cache_target = self.classes[target_class_id] 
       if len(cache_target) >= CAPACITY: # Target is Full! (Trigger LRU here)
           victim = self._evict_from_full(cache_target, class_order_excluding_self?)
           # Move victim to next available non-full? Or the one we just filled?
           # Spec: "Put in other < 45". 
           if len(class_list_not_includes(target)) > 0 and has_free_slot():
               find_next_full_or_nonfull_for_victim() -> insert there.
               Then, victim is gone from target. Target now < Capacity. Insert new student to TARGET.
       
       Else: (Target not full) 
           Just append New Student to Target.
    
    ```

### File: `main.py` or Entry Point
- Instantiates `ClassSchedulerManager`.
- Initializes dummy Classes A, B, C with random data <= 45.
- Loops to test adding students up to overflow scenarios.
- Prints logs of evictions and new class creations.

## 5. 关键函数/类定义

### Class: `Student` (Dataclass or SimpleDict Wrapper)
```python
@dataclass
class StudentRecord: # Using internal dict for O(1) access speed, wrapped logically? 
    # Actually use simple Dict inside OrderedDict to avoid class overhead unless needed.
    id: int
    name: str
    last_called_time: float = field(default_factory=time.time)
```

### Class: `ClassCache` (Inherits from LRU Logic using OrderedDict internally but explicit methods)
**Methods**:
- `_evict():`: Pops item with lowest priority (oldest time). Returns `(student_id, student_record)` or just the record. If tie in time? Keep oldest insertion order if times equal? Use `OrderedDict` popitem(last=False).
    - *Tie-breaker*: If timestamps are same (unlikely but possible), use ID to determine "older"? Or strict `<`. Requirement: "prefer earliest timestamp". 

### Class: `ClassSchedulerManager`
**Methods**:
- `_find_victim(cache)`: Returns the student record of least recently used.
    - Logic: Iterate keys in reverse? No, `OrderedDict` stores insertion order. To support LRU based on time, we must **move updated items to end**. 
      ```python
      def update_access(student):
          # Removes from current pos and re-adds at END (Most Recently Used)
           return self.cache.pop(self.get_id_of_student), [val]... 
       ```
- `_transfer_evicted_victim(victim_record, target_cache_list)`: Finds next available cache. If all full -> Create New Cache in `self.classes`.

## 6. 数据模型/数据库设计 (In-Memory Schema)

### Global State Map (`scheduler`)
`{ "A": {"_cache": OrderedDict}, "B": {...} ... }`

### Class Instance `_students_map`
Key: `StudentID` (int). 
Value: `{ 'id': ..., 'name': ..., '_last_time': float, '_calls': int }`.

**Constraint**: Max size 45. 

## 7. 错误处理策略
- **Empty Key Handling (`pop(key)`)**: Wrap in try-except or use `.get()` then handle `None` logic? 
    - Use `OrderedDict.get(id)`. If not found -> Return None (Shouldn't happen for valid access).
- **Full System**: When no slots exist, simply create new ID ("E"). No exception raised.
- **Concurrency**: Wrap critical sections of `_evict`, `_insert` with a global lock (`threading.Lock`) to prevent race conditions where two threads check "not full" simultaneously and both try to evict/insert causing corruption or double-eviction.

## 8. 测试要求 (Unit Tests)
- **Test Case: Overload**. Fill A-D completely. Add new student -> Assert New Class E created, Student added, no exception raised.
- **Test Case: Eviction Order**. Populate A with students at t=10s and t=20s interval intervals to create a clear LRU victim. Insert trigger evict -> Check if oldest (t=?) is removed first. 
  - *Implementation Note*: Use `time.time()` for high resolution timestamps, but for testing use mock times (`mock_time`) passed into `_update_access`.
- **Test Case: Tie-Breaker**. Two students added at t=t0+1 and updated both? Hard to force perfect ties with time. Instead simulate by setting same timestamp manually if needed or verify stable sorting behavior (first insertion wins).

## 9. 实施细节与注意事项
- **Thread Safety**: The requirement explicitly mentions "threading.Lock". Wrap `_add_student`, `_evict_victim` methods inside `with self.lock:` blocks.
- **LRU Logic Implementation Detail**: 
    To implement LRU based on Time in Python:
    ```python
    # Access logic (Make Recently)
    def access(self, key):
        val = self._data.pop(key)
        if val is not None:
            del self._data[key]
            self._cache[val['id']] = val  # Inserts at END -> Most Recent
            
    # Evict Logic (Least Used/Old)
    def evict(self):
         return self._cache.popitem(last=False)[1] 
    ```
- **Config**: Hardcode `MAX_CAPACITY=45`. If needed, make it configurable via constructor or class variable but default to 45.

--- 

*End of Specification.*