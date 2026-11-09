# Release builds keep minification off for the assessment (see app/build.gradle.kts).
-keepattributes *Annotation*, InnerClasses
-keep,includedescriptorclasses class com.series76.assistant.**$$serializer { *; }
