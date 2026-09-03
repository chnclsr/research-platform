# Docling Parse 7.15.0 deneysel CMake patch izleri

Bu klasör production kodu değildir. `docling-parse==7.15.0` paketini CPython
3.14 free-threaded ortamında kaynak koddan kurma denemesi sırasında `/tmp` altındaki
geçici sdist üzerinde değiştirilen CMake dosyalarının kopyasıdır.

Amaç, Docling runtime testine geçebilmek için packaging engelinin ne kadar ilerletildiğini
kaybetmeden belgelemektir. Bu dosyalarla şu kapılar aşıldı:

- qpdf/jpeg/openjpeg/lcms2/freetype static library çıktıları CMake/Ninja tarafında
  `BUILD_BYPRODUCTS` olarak görünür hale getirildi.
- qpdf Linux alt derlemesi static çıktıya zorlandı.
- LCMS2 configure adımına `--disable-dependency-tracking` eklendi.
- qpdf alt derlemesine vendored external dizin `CMAKE_PREFIX_PATH` olarak geçirildi.

Sonraki engel bizim repo kodundan değil, `docling-parse` native dependency zincirinden
geliyor: qpdf alt derlemesi kendi configure adımında zlib/libjpeg çözümlemesini
tamamlayamıyor ve `libqpdf.a` oluşmuyor.

Bu klasör, “Docling free-threaded runtime testi hiç denenmedi” dememek için değil;
deneyin packaging sınırına kadar götürüldüğünü ve kalan işin upstream/packaging işi
olduğunu kanıtlamak için tutulur.
