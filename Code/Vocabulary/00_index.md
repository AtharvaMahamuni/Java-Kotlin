# Android Vocabulary — Master Index

Quick-recall notes for **185 interview questions** across Java/JVM, Kotlin, Android Framework,
Build System, and Architecture. Each answer: Definition → Core Idea → How it Works → Example → Interview Insight.

---

## Files

| File | Section | Questions |
|------|---------|-----------|
| [01_java_core_language.md](01_java_core_language.md) | Java Core Language | Q1–Q19 |
| [02_jvm_architecture_memory.md](02_jvm_architecture_memory.md) | JVM Architecture, Memory, Generics | Q20–Q41 |
| [03_java_serialization_concurrency.md](03_java_serialization_concurrency.md) | Serialization & Concurrency | Q42–Q52 |
| [04_kotlin_basics_classes.md](04_kotlin_basics_classes.md) | Kotlin Basics, Classes, Functional | Q53–Q82 |
| [05_kotlin_collections_coroutines.md](05_kotlin_collections_coroutines.md) | Collections & Coroutines | Q83–Q91 |
| [06_android_framework_components.md](06_android_framework_components.md) | Android Framework & Components | Q92–Q132 |
| [07_android_build_system.md](07_android_build_system.md) | Build System (Gradle, R8, APK) | Q133–Q166 |
| [08_android_architecture_performance.md](08_android_architecture_performance.md) | Architecture & Performance | Q167–Q185 |

---

## All 185 Questions — Direct Links

### Section 1: Java Core Language
[Q1 Class](01_java_core_language.md#q1-what-is-a-class) |
[Q2 Object](01_java_core_language.md#q2-what-is-an-object) |
[Q3 Encapsulation](01_java_core_language.md#q3-what-is-encapsulation) |
[Q4 Inheritance](01_java_core_language.md#q4-what-is-inheritance) |
[Q5 Polymorphism](01_java_core_language.md#q5-what-is-polymorphism) |
[Q6 Abstraction](01_java_core_language.md#q6-what-is-abstraction) |
[Q7 Overloading](01_java_core_language.md#q7-what-is-method-overloading) |
[Q8 Overriding](01_java_core_language.md#q8-what-is-method-overriding) |
[Q9 Interface](01_java_core_language.md#q9-what-is-an-interface) |
[Q10 Abstract Class](01_java_core_language.md#q10-what-is-an-abstract-class) |
[Q11 Interface vs Abstract](01_java_core_language.md#q11-difference-between-interface-and-abstract-class) |
[Q12 Constructor](01_java_core_language.md#q12-what-is-a-constructor) |
[Q13 Constructor Overloading](01_java_core_language.md#q13-what-is-constructor-overloading) |
[Q14 Static Method](01_java_core_language.md#q14-what-is-a-static-method) |
[Q15 Static Variable](01_java_core_language.md#q15-what-is-a-static-variable) |
[Q16 final](01_java_core_language.md#q16-what-is-the-final-keyword) |
[Q17 Immutability](01_java_core_language.md#q17-what-is-immutability) |
[Q18 this](01_java_core_language.md#q18-what-is-the-this-keyword) |
[Q19 super](01_java_core_language.md#q19-what-is-the-super-keyword)

### Section 2: JVM Architecture
[Q20 JVM](02_jvm_architecture_memory.md#q20-what-is-the-jvm) |
[Q21 JDK](02_jvm_architecture_memory.md#q21-what-is-the-jdk) |
[Q22 JRE](02_jvm_architecture_memory.md#q22-what-is-the-jre) |
[Q23 Compilation](02_jvm_architecture_memory.md#q23-what-happens-when-java-code-is-compiled) |
[Q24 Bytecode](02_jvm_architecture_memory.md#q24-what-is-bytecode) |
[Q25 Class Loading](02_jvm_architecture_memory.md#q25-what-is-class-loading) |
[Q26 Classloader](02_jvm_architecture_memory.md#q26-what-is-the-classloader) |
[Q27 Bootstrap CL](02_jvm_architecture_memory.md#q27-what-is-the-bootstrap-classloader) |
[Q28 Extension CL](02_jvm_architecture_memory.md#q28-what-is-the-extension-classloader) |
[Q29 Application CL](02_jvm_architecture_memory.md#q29-what-is-the-application-classloader)

### Section 2: Memory Model
[Q30 Heap](02_jvm_architecture_memory.md#q30-what-is-heap-memory) |
[Q31 Stack](02_jvm_architecture_memory.md#q31-what-is-stack-memory) |
[Q32 Metaspace](02_jvm_architecture_memory.md#q32-what-is-the-method-area--metaspace) |
[Q33 GC](02_jvm_architecture_memory.md#q33-what-is-garbage-collection) |
[Q34 GC Roots](02_jvm_architecture_memory.md#q34-what-are-gc-roots) |
[Q35 Memory Leak](02_jvm_architecture_memory.md#q35-what-is-a-memory-leak) |
[Q36 Allocation](02_jvm_architecture_memory.md#q36-what-is-object-allocation)

### Section 2: Generics
[Q37 Generics](02_jvm_architecture_memory.md#q37-what-are-generics) |
[Q38 Type Erasure](02_jvm_architecture_memory.md#q38-what-is-type-erasure) |
[Q39 Why Generics](02_jvm_architecture_memory.md#q39-why-do-generics-exist) |
[Q40 Bounded](02_jvm_architecture_memory.md#q40-what-are-bounded-generics) |
[Q41 Wildcard](02_jvm_architecture_memory.md#q41-what-is-wildcard-usage-in-generics)

### Section 3: Serialization & Concurrency
[Q42 Serialization](03_java_serialization_concurrency.md#q42-what-is-serialization) |
[Q43 Deserialization](03_java_serialization_concurrency.md#q43-what-is-deserialization) |
[Q44 Serializable](03_java_serialization_concurrency.md#q44-what-is-the-serializable-interface) |
[Q45 Serializable vs Externalizable](03_java_serialization_concurrency.md#q45-difference-between-serializable-and-externalizable) |
[Q46 Thread](03_java_serialization_concurrency.md#q46-what-is-a-thread) |
[Q47 Process](03_java_serialization_concurrency.md#q47-what-is-a-process) |
[Q48 Multithreading](03_java_serialization_concurrency.md#q48-what-is-multithreading) |
[Q49 Synchronization](03_java_serialization_concurrency.md#q49-what-is-synchronization) |
[Q50 Race Condition](03_java_serialization_concurrency.md#q50-what-is-a-race-condition) |
[Q51 Deadlock](03_java_serialization_concurrency.md#q51-what-is-a-deadlock) |
[Q52 Thread Safety](03_java_serialization_concurrency.md#q52-what-is-thread-safety)

### Section 4: Kotlin Basics
[Q53 Kotlin](04_kotlin_basics_classes.md#q53-what-is-kotlin) |
[Q54 Null Safety](04_kotlin_basics_classes.md#q54-what-is-null-safety) |
[Q55 Nullable Type](04_kotlin_basics_classes.md#q55-what-is-a-nullable-type) |
[Q56 !!](04_kotlin_basics_classes.md#q56-what-is-the--operator) |
[Q57 ?.](04_kotlin_basics_classes.md#q57-what-is-the-safe-call-operator-) |
[Q58 ?:](04_kotlin_basics_classes.md#q58-what-is-the-elvis-operator-) |
[Q59 Type Inference](04_kotlin_basics_classes.md#q59-what-is-type-inference) |
[Q60 Primary Constructor](04_kotlin_basics_classes.md#q60-what-is-a-primary-constructor) |
[Q61 Secondary Constructor](04_kotlin_basics_classes.md#q61-what-is-a-secondary-constructor)

### Section 4: Kotlin Classes
[Q62 Data Class](04_kotlin_basics_classes.md#q62-what-is-a-data-class) |
[Q63 Data Class Methods](04_kotlin_basics_classes.md#q63-what-methods-are-automatically-generated-in-a-data-class) |
[Q64 Sealed Class](04_kotlin_basics_classes.md#q64-what-is-a-sealed-class) |
[Q65 Enum Class](04_kotlin_basics_classes.md#q65-what-is-an-enum-class) |
[Q66 Object Declaration](04_kotlin_basics_classes.md#q66-what-is-an-object-declaration) |
[Q67 Companion Object](04_kotlin_basics_classes.md#q67-what-is-a-companion-object) |
[Q68 Nested Classes](04_kotlin_basics_classes.md#q68-what-are-nested-classes) |
[Q69 Inner Classes](04_kotlin_basics_classes.md#q69-what-are-inner-classes)

### Section 4: Functional & Type System
[Q70 Lambda](04_kotlin_basics_classes.md#q70-what-is-a-lambda-expression) |
[Q71 Higher-Order](04_kotlin_basics_classes.md#q71-what-is-a-higher-order-function) |
[Q72 Inline](04_kotlin_basics_classes.md#q72-what-is-an-inline-function) |
[Q73 crossinline](04_kotlin_basics_classes.md#q73-what-is-crossinline) |
[Q74 noinline](04_kotlin_basics_classes.md#q74-what-is-noinline) |
[Q75 Covariance](04_kotlin_basics_classes.md#q75-what-is-covariance) |
[Q76 Contravariance](04_kotlin_basics_classes.md#q76-what-is-contravariance) |
[Q77 Invariance](04_kotlin_basics_classes.md#q77-what-is-invariance) |
[Q78 Star Projection](04_kotlin_basics_classes.md#q78-what-is-star-projection) |
[Q79 Extension Functions](04_kotlin_basics_classes.md#q79-what-are-extension-functions) |
[Q80 Extension Properties](04_kotlin_basics_classes.md#q80-what-are-extension-properties) |
[Q81 Scope Functions](04_kotlin_basics_classes.md#q81-what-are-scope-functions) |
[Q82 let/run/apply/also/with](04_kotlin_basics_classes.md#q82-difference-between-let-run-apply-also-and-with)

### Section 5: Collections & Coroutines
[Q83 List vs MutableList](05_kotlin_collections_coroutines.md#q83-difference-between-list-and-mutablelist) |
[Q84 Set vs HashSet](05_kotlin_collections_coroutines.md#q84-difference-between-set-and-hashset) |
[Q85 Map vs HashMap](05_kotlin_collections_coroutines.md#q85-difference-between-map-and-hashmap) |
[Q86 IntArray vs Array<Int>](05_kotlin_collections_coroutines.md#q86-difference-between-intarray-and-arrayint) |
[Q87 Coroutine](05_kotlin_collections_coroutines.md#q87-what-is-a-coroutine) |
[Q88 Suspend Function](05_kotlin_collections_coroutines.md#q88-what-is-a-suspend-function) |
[Q89 Coroutine Scope](05_kotlin_collections_coroutines.md#q89-what-is-a-coroutine-scope) |
[Q90 Dispatcher](05_kotlin_collections_coroutines.md#q90-what-is-a-dispatcher) |
[Q91 Structured Concurrency](05_kotlin_collections_coroutines.md#q91-what-is-structured-concurrency)

### Section 6: Android Framework
[Q92 Framework](06_android_framework_components.md#q92-what-is-the-android-framework) |
[Q93 Components](06_android_framework_components.md#q93-what-are-the-main-android-application-components) |
[Q94 Manifest](06_android_framework_components.md#q94-what-is-androidmanifestxml) |
[Q95 Application Class](06_android_framework_components.md#q95-what-is-the-application-class) |
[Q96 Activity](06_android_framework_components.md#q96-what-is-an-activity) |
[Q97 Activity Lifecycle](06_android_framework_components.md#q97-what-is-the-activity-lifecycle) |
[Q98 Config Change](06_android_framework_components.md#q98-what-happens-during-a-configuration-change) |
[Q99 Back Stack](06_android_framework_components.md#q99-what-is-the-activity-back-stack) |
[Q100 Launch Modes](06_android_framework_components.md#q100-what-are-launch-modes) |
[Q101 Fragment](06_android_framework_components.md#q101-what-is-a-fragment) |
[Q102 Fragment Lifecycle](06_android_framework_components.md#q102-what-is-the-fragment-lifecycle) |
[Q103 FragmentManager](06_android_framework_components.md#q103-what-is-fragmentmanager) |
[Q104 add vs replace](06_android_framework_components.md#q104-difference-between-add-and-replace) |
[Q105 Intent](06_android_framework_components.md#q105-what-is-an-intent) |
[Q106 Explicit vs Implicit](06_android_framework_components.md#q106-difference-between-explicit-and-implicit-intents) |
[Q107 Intent Filter](06_android_framework_components.md#q107-what-is-an-intent-filter) |
[Q108 Intent Extras](06_android_framework_components.md#q108-what-are-intent-extras) |
[Q109 Bundle](06_android_framework_components.md#q109-what-is-a-bundle) |
[Q110 Bundle data passing](06_android_framework_components.md#q110-how-is-bundle-used-to-pass-data) |
[Q111 Bundle limits](06_android_framework_components.md#q111-what-are-the-limitations-of-bundle) |
[Q112 Service](06_android_framework_components.md#q112-what-is-a-service) |
[Q113 Started Service](06_android_framework_components.md#q113-what-is-a-started-service) |
[Q114 Bound Service](06_android_framework_components.md#q114-what-is-a-bound-service) |
[Q115 Foreground Service](06_android_framework_components.md#q115-what-is-a-foreground-service) |
[Q116 BroadcastReceiver](06_android_framework_components.md#q116-what-is-a-broadcastreceiver) |
[Q117 System Broadcast](06_android_framework_components.md#q117-what-is-a-system-broadcast) |
[Q118 Ordered Broadcast](06_android_framework_components.md#q118-what-is-an-ordered-broadcast) |
[Q119 ContentProvider](06_android_framework_components.md#q119-what-is-a-contentprovider) |
[Q120 Content URI](06_android_framework_components.md#q120-what-is-a-content-uri) |
[Q121 CRUD](06_android_framework_components.md#q121-what-are-the-crud-operations-in-contentprovider) |
[Q122 WorkManager](06_android_framework_components.md#q122-what-is-workmanager) |
[Q123 JobScheduler](06_android_framework_components.md#q123-what-is-jobscheduler) |
[Q124 Handler](06_android_framework_components.md#q124-what-is-a-handler) |
[Q125 Looper](06_android_framework_components.md#q125-what-is-a-looper) |
[Q126 Parcelable](06_android_framework_components.md#q126-what-is-parcelable) |
[Q127 Serializable Android](06_android_framework_components.md#q127-what-is-serializable-android-context) |
[Q128 AIDL](06_android_framework_components.md#q128-what-is-aidl) |
[Q129 ANR](06_android_framework_components.md#q129-what-is-anr) |
[Q130 UI Thread](06_android_framework_components.md#q130-what-is-the-mainui-thread) |
[Q131 Process Death](06_android_framework_components.md#q131-what-is-process-death) |
[Q132 LMK](06_android_framework_components.md#q132-what-is-low-memory-killer)

### Section 7: Build System
[Q133 Gradle](07_android_build_system.md#q133-what-is-gradle) |
[Q134 AGP](07_android_build_system.md#q134-what-is-the-android-gradle-plugin) |
[Q135 Build Script](07_android_build_system.md#q135-what-is-a-gradle-build-script) |
[Q136 build.gradle](07_android_build_system.md#q136-what-is-buildgradle) |
[Q137 settings.gradle](07_android_build_system.md#q137-what-is-settingsgradle) |
[Q138 gradle.properties](07_android_build_system.md#q138-what-is-gradleproperties) |
[Q139 local.properties](07_android_build_system.md#q139-what-is-localproperties) |
[Q140 Gradle Task](07_android_build_system.md#q140-what-is-a-gradle-task) |
[Q141 compileSdk](07_android_build_system.md#q141-what-is-compilesdkversion) |
[Q142 minSdk](07_android_build_system.md#q142-what-is-minsdkversion) |
[Q143 targetSdk](07_android_build_system.md#q143-what-is-targetsdkversion) |
[Q144 compileSdk vs targetSdk](07_android_build_system.md#q144-difference-between-compile-sdk-and-target-sdk) |
[Q145 Build Types](07_android_build_system.md#q145-what-are-build-types) |
[Q146 Debug](07_android_build_system.md#q146-what-is-debug-build-type) |
[Q147 Release](07_android_build_system.md#q147-what-is-release-build-type) |
[Q148 Product Flavors](07_android_build_system.md#q148-what-are-product-flavors) |
[Q149 Types vs Flavors](07_android_build_system.md#q149-difference-between-build-types-and-product-flavors) |
[Q150 Dependencies](07_android_build_system.md#q150-what-are-gradle-dependencies) |
[Q151 Resolution](07_android_build_system.md#q151-what-is-dependency-resolution) |
[Q152 Transitive](07_android_build_system.md#q152-what-is-a-transitive-dependency) |
[Q153 implementation vs api](07_android_build_system.md#q153-difference-between-implementation-and-api) |
[Q154 ProGuard](07_android_build_system.md#q154-what-is-proguard) |
[Q155 R8](07_android_build_system.md#q155-what-is-r8) |
[Q156 ProGuard Problem](07_android_build_system.md#q156-what-problem-does-proguard-solve) |
[Q157 Shrinking](07_android_build_system.md#q157-what-is-code-shrinking) |
[Q158 Obfuscation](07_android_build_system.md#q158-what-is-code-obfuscation) |
[Q159 ProGuard Rule](07_android_build_system.md#q159-what-is-a-proguard-rule) |
[Q160 -keep](07_android_build_system.md#q160-what-does--keep-mean-in-proguard) |
[Q161 APK](07_android_build_system.md#q161-what-is-an-apk) |
[Q162 AAB](07_android_build_system.md#q162-what-is-an-aab-android-app-bundle) |
[Q163 APK vs AAB](07_android_build_system.md#q163-difference-between-apk-and-aab) |
[Q164 DEX](07_android_build_system.md#q164-what-is-dex) |
[Q165 Multidex](07_android_build_system.md#q165-what-is-multidex) |
[Q166 64K limit](07_android_build_system.md#q166-why-does-the-64k-method-limit-exist)

### Section 8: Architecture & Performance
[Q167 MVVM](08_android_architecture_performance.md#q167-what-is-mvvm-architecture) |
[Q168 ViewModel](08_android_architecture_performance.md#q168-what-is-viewmodel) |
[Q169 ViewModel Problem](08_android_architecture_performance.md#q169-what-problem-does-viewmodel-solve) |
[Q170 LiveData](08_android_architecture_performance.md#q170-what-is-livedata) |
[Q171 Flow](08_android_architecture_performance.md#q171-what-is-flow) |
[Q172 LifecycleOwner](08_android_architecture_performance.md#q172-what-is-lifecycleowner) |
[Q173 Binder](08_android_architecture_performance.md#q173-what-is-binder) |
[Q174 Android IPC](08_android_architecture_performance.md#q174-what-is-android-ipc) |
[Q175 Zygote](08_android_architecture_performance.md#q175-what-is-zygote) |
[Q176 ActivityManager](08_android_architecture_performance.md#q176-what-is-activitymanager) |
[Q177 PackageManager](08_android_architecture_performance.md#q177-what-is-packagemanager) |
[Q178 UI Thread](08_android_architecture_performance.md#q178-what-is-the-android-ui-thread) |
[Q179 Choreographer](08_android_architecture_performance.md#q179-what-is-choreographer) |
[Q180 Frame](08_android_architecture_performance.md#q180-what-is-a-frame-in-android-rendering) |
[Q181 Jank](08_android_architecture_performance.md#q181-what-causes-ui-jank) |
[Q182 Memory Leak](08_android_architecture_performance.md#q182-what-is-a-memory-leak-in-android) |
[Q183 ANR causes](08_android_architecture_performance.md#q183-what-causes-anr) |
[Q184 StrictMode](08_android_architecture_performance.md#q184-what-is-strictmode) |
[Q185 Profiler](08_android_architecture_performance.md#q185-what-is-the-android-profiler)

---

## Quick Topic Lookup

| I need to recall... | Go to |
|---|---|
| 4 pillars of OOP | [Q3–Q6](01_java_core_language.md#q3-what-is-encapsulation) |
| Interface vs Abstract Class | [Q11](01_java_core_language.md#q11-difference-between-interface-and-abstract-class) |
| JVM memory regions | [Q30–Q32](02_jvm_architecture_memory.md#q30-what-is-heap-memory) |
| Why memory leaks happen | [Q34–Q35](02_jvm_architecture_memory.md#q34-what-are-gc-roots) |
| Kotlin null safety operators | [Q54–Q58](04_kotlin_basics_classes.md#q54-what-is-null-safety) |
| Data class auto-methods | [Q63](04_kotlin_basics_classes.md#q63-what-methods-are-automatically-generated-in-a-data-class) |
| Sealed class for UiState | [Q64](04_kotlin_basics_classes.md#q64-what-is-a-sealed-class) |
| Scope functions table | [Q82](04_kotlin_basics_classes.md#q82-difference-between-let-run-apply-also-and-with) |
| Coroutines vs threads | [Q87](05_kotlin_collections_coroutines.md#q87-what-is-a-coroutine) |
| Activity lifecycle callbacks | [Q97](06_android_framework_components.md#q97-what-is-the-activity-lifecycle) |
| Fragment TWO lifecycles | [Q101–Q102](06_android_framework_components.md#q101-what-is-a-fragment) |
| Why ViewModel survives rotation | [Q168–Q169](08_android_architecture_performance.md#q168-what-is-viewmodel) |
| APK vs AAB | [Q163](07_android_build_system.md#q163-difference-between-apk-and-aab) |
| R8 / ProGuard -keep rules | [Q159–Q160](07_android_build_system.md#q159-what-is-a-proguard-rule) |
| ANR timeouts | [Q183](08_android_architecture_performance.md#q183-what-causes-anr) |
| How Zygote works | [Q175](08_android_architecture_performance.md#q175-what-is-zygote) |
| 16ms frame budget | [Q180–Q181](08_android_architecture_performance.md#q180-what-is-a-frame-in-android-rendering) |
