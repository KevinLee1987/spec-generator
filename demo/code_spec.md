# Class LRU Scheduler Implementation Specification

## 1. Project Background & Objective
The objective is to implement a "Class Transfer Student" module using an **LRU (Least Recently Used)** eviction strategy. This system manages student lists and headcount for multiple classes.
When a specific class reaches its capacity limit (**45 students**) and receives a new transfer student, the system automatically identifies the student who has been **"named last"** (LRU candidate) within that class, evicts them from the current class, and attempts to move them to an available slot in another non-full class. This process cascades recursively until a spot is found or a new empty class is created.

## 2. Technical Constraints & Stack
- **Language**: Python 3.8+
- **Core Framework**: Standard Library only (No external dependencies like `cachetools` required).
- **Data Structure Implementation**: 
  - Must use `collections.OrderedDict` to simulate the Hash Map + Doubly Linked List behavior.
  - **OrderedDict** Key: Student ID (Hash).
  - **OrderedDict** Value: Student Object/Details.
  - **Access Order**: Managed via `.move_to_end(key)` for "Recently Used" and `.popitem(last=False)` for "Least Recently Used".
- **Concurrency**: Single-threaded assumption per document Section 8. No threading locks required unless future scaling is added.

## 3. Existing Code Structure Analysis
Based on the provided documentation, the codebase will consist of a single module containing:
1.  **`StudentManager` Class**: The global singleton or instance managing all classes and handling the cross-class transfer logic.
2.  **`ClassLRUCache` Class**: A wrapper extending `OrderedDict` to represent a specific class, enforcing capacity limits and LRU eviction policies internally.

*Note: No existing files are provided in the prompt context, but the spec assumes a clean slate based on the "Development Document". The implementation must create these classes from scratch.*

## 4. File Manifest & Detailed Description

### File: `class_lru_scheduler.py`
This single file will contain all logic required to run the system.

#### Classes to Implement:
1.  **`Student`**: Data model for a student.
2.  **`ClassLRUCache`**: Represents a Class. Inherits from/Encapsulates `OrderedDict`. Handles internal eviction logic.
3.  **`StudentManager`**: Global manager. Holds `dict[class_id: ClassLRUCache]`. Handles public API and cascading transfer logic.

## 5. Key Function/Class Definitions

### 5.1 Class: `Student`
| Method | Signature | Description |
| :--- | :--- | :--- |
| **Constructor** | `__init__(self, student_id, name)` | Initializes unique ID and name. |
| **Getter** | `get_id(self)` -> `str`/`int` | Returns the student ID (used as LRU Cache key). |
| **Getter** | `get_name(self)` -> `str` | Returns student name. |

### 5.2 Class: `ClassLRUCache` (Internal Implementation)
This class wraps `OrderedDict`. It does *not* expose internal OrderedDict methods directly to the public API but manages them for eviction.

| Method | Signature | Parameters | Return Value | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Constructor** | `__init__(self, class_id, capacity=45)` | `class_id`: str/unique ID<br>`capacity`: int (default 45) | `None` | Initializes empty cache and sets limits. |
| **Insert** | `_insert(self, student: Student)` -> `bool` | `student`: `Student` object | `bool` | Adds student. Throws error if full (handled by Manager). Internally calls `move_to_end`. |
| **Evict LRU** | `_evict_lru(self)` -> `Student` | - | `Student` or `None` | Checks capacity. If full, `popitem(last=False)` to remove oldest student. Returns the evicted student object. <br>*Constraint: Must not return if count < capacity.* |
| **Access** | `_access(self, student_id: str)` -> `bool` | `student_id`: str | `bool` | If student exists in this class, calls `move_to_end(student_id)`. Returns `True` on success, `False` otherwise. |
| **Get Size** | `_get_count(self)` -> `int` | - | `int` | Returns `len(OrderedDict)`. |

### 5.3 Class: `StudentManager` (Public API)
| Method | Signature | Parameters | Return Value | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Initialize** | `initialize(self, classes_config: dict)` | `classes_config`: `{class_id: [] or None}` | `None` | Loads initial state. If a class has students, populates cache. Note: Initial load assumes valid ID structure. |
| **Add Transfer**| `add_transfer_student(self, class_id: str, student: Student)` -> `ResultDict` | `class_id`: str<br>`student`: `Student` | `dict` | Attempts to add `student` to `class_id`. <br>1. If target < 45: Add directly.<br>2. If target == 45: Evict LRU from target -> Find new home for evicted student (recursive/iterative).<br>3. If all full: Create new empty class -> Place evicted here.<br>Returns dict with `success`, `final_class_id`, `evicted_student_id`. |
| **Record Attendance** | `record_attendance(self, class_id: str, student_id: str)` -> `bool` | `class_id`: str<br>`student_id`: str | `bool` | Marks student as "Used". Moves entry to Head of linked list. Returns `False` if student not found or class full (should not happen). |
| **Get Status** | `get_class_status(self)` -> `dict` | - | `dict` | Returns `{class_id: {"name": id, "count": current, "capacity": 45}}`. |

### 5.4 Internal Helper Functions (within `StudentManager`)
- **`_find_or_create_empty_class()`** -> `ClassLRUCache` or `None`
    - Iterates through internal `self.classes.values()`.
    - If a class with `< 45` students is found, return it.
    - If no such class exists (all full), create a new `ClassLRUCache` object (init with 0 count) and return it.

## 6. Data Models & Database Design

### 6.1 Memory Layout
No external database is used for the core logic. The state resides in memory structures:
1.  **Global Map**: `self.classes = {}` 
    - Keys: Class IDs (str).
    - Values: Instances of `ClassLRUCache`.
2.  **Student Object**: Standard Python class.
3.  **LRU Implementation**: Internal to `ClassLRUCache` using `OrderedDict`.

## 7. Error Handling Strategy
- **Full Capacity Attempt**: Handled automatically by the eviction logic. The `add_transfer_student` method should never raise an exception for a full class unless there is a memory error (impossible) or logic bug. It returns a status indicating that an eviction occurred.
- **Invalid Student ID in Attendance**: If `student_id` does not exist in any class or exists in a different class, return `False`.
- **Initialization**: If `classes_config` provides students with duplicate IDs across the system, behavior is undefined (recommendation: ensure uniqueness).

## 8. Testing Requirements

### 8.1 Unit Test Cases to Implement
1.  **Test Empty Insertion**: 
    - Setup: 1 Class (0/45). 
    - Action: Add Student S1. 
    - Assert: Count = 1, S1 is Head (First in OD).
2.  **Test Direct Insertion**: 
    - Setup: 1 Class (40/45), Classes=[S1..S40]. 
    - Action: Add S_new. 
    - Assert: Count=41, S_new is Head.
3.  **Test Single Eviction Cascade**: 
    - Setup: Class A (45/45), Class B (40/45).
    - State A: [S1..S45], S2 is LRU (Tail).
    - Action: Add S_new to A -> Add to system.
    - Expected Flow: 
      1. S_new fails direct insert (A full) or simply triggers logic? *Correction*: The doc says "When inserting transfer student". If target full, evict. 
      2. Evict S2 from A. 
      3. Insert S2 into B. 
      4. Update B LRU order.
    - Assert: A count=44 (S_new inserted? Wait, logic check: The doc says "When inserting a transfer student to Class A... if A full, evict". Does the *new* student enter A? Yes. So A becomes 45 again. S2 goes to B.)
    - **Result Verification**: 
      - Class A: Contains S_new + {S1..S45} minus {S2}. Count=45. S_new is Head.
      - Class B: Contains original 40 + S2. Count=41.
4.  **Test Chain Reaction (All Full)**: 
    - Setup: A, B, C all (45/45).
    - Action: Add S_new to A.
    - Flow: Evict from A -> Try B -> B Evicts -> Try C -> C Evicts -> Create D -> Insert there.
    - Assert: S_old moved to D. D created. A, B, C maintain 45 (with new occupants).
5.  **Test Attendance Update**: 
    - Setup: Class A has [S1..S45]. 
    - Action: `record_attendance(A, "S20")`.
    - Assert: In OrderedDict, "S20" is moved to the end (most recent). Next `popitem` must not return "S20".

## 9. Implementation Details & Edge Cases

### 9.1 LRU Order Maintenance
- **Insertion**: When adding a student, immediately call `od.move_to_end(student_id)`.
- **Eviction**: Use `od.popitem(last=False)` which returns and removes the first item (oldest).
- **Update**: Use `od.move_to_end(student_id)` after successful attendance recording.

### 9.2 Cascading Logic Implementation
The method `add_transfer_student` must handle the evicted student immediately:
```python
# Pseudocode logic for add_transfer_student
def add_transfer_student(self, class_id, student):
    target = self.classes.get(class_id)
    
    # Scenario A: Target not full (or creating new empty one automatically?)
    # Based on doc: "If Class A < 45: Direct Insert". 
    # So if target is full (==45), we trigger eviction.
    
    if len(target) < self.MAX_CAPACITY:
        target._insert(student)
        return {"success": True, "class_id": class_id}

    # Scenario B: Target Full (==45)
    # 1. Evict LRU from Target
    evicted_student = target._evict_lru() 
    
    # The new student goes into the slot vacated? 
    # Doc says: "If Class A full... identify LRU... move to other class". 
    # Does the NEW student enter Class A? 
    # Interpretation: Yes, "Insert Transfer Student" implies moving someone IN. 
    # If we evict S2 to make room for S_new (and potentially others).
    
    target._insert(student) # Put new student in
    
    # 2. Move Evicted Student to Next Class
    recipient = self._find_or_create_empty_class() # Iterate all classes excluding target? 
                                                 # Wait, if we just inserted 'student', target is still full? 
                                                 # No. We evicted 1 person (S2). Target had 45. Now 44. 
                                                 # Then we insert S_new -> Target has 45 again. 
                                                 # So we successfully placed S_new.
                                                 # We just need to find a home for S2 (evicted).
    
    while recipient:
        if len(recipient) < self.MAX_CAPACITY:
            recipient._insert(evicted_student)
            evicted_student = None # Done
            break
        
        # Recipient is full. Evict from Recipient too? 
        # "If Class B is also full... repeat eviction logic".
        # Yes, chain reaction.
        
        next_evicted = recipient._evict_lru()
        if next_evicted:
            # Continue loop to find new home for 'next_evicted'
            # We need to search for a home again. 
            # Optimization: Search all classes for empty slot.
            evicted_student = next_evicted
            
    return {"success": True, "evicted_id": evicted_student.id if evicted_student else None}
```

### 9.3 Finding Empty Slot Implementation (`_find_or_create_empty_class`)
- Iterate `self.classes.values()`.
- If `len(class_obj) < 45`: Return `class_obj` and break loop.
- If loop finishes without finding slot: Create new `ClassLRUCache("NEW_CLASS_" + str(self.class_count))` and return it.
- *Optimization*: Maintain a set of indices or a linked list of classes to avoid O(N) scan if N grows large (though doc says linear scan is acceptable for small N, good to note).

## 10. Deployment Notes
- Run using standard Python 3 environment.
- No installation steps required (`pip install` not needed).
- Input validation assumes valid integers/strings as per `Student` definition.