import ctypes
from ctypes import c_bool, c_char_p, c_longlong, c_ulong, c_ulonglong, c_void_p, c_wchar_p, POINTER


# Constants
INVALID_HANDLE = ctypes.c_void_p(-1)
 
# IOCTLs - see WinIoCtl.h
# (DEVTYPE << 16 | ACCESS << 14 | FUNC << 2 | METHOD)
# ACCESS_ANY / _SPECIAL = 0, ACCESS_READ = 1, ACCESS_WRITE = 2
# METHOD_BUFFERED = 0, _IN_DIRECT = 1, _OUT_DIRECT = 2, _NEITHER = 3
FSCTL_IS_VOLUME_MOUNTED              = 0x00090028   # func 10, method 0
FSCTL_GET_VOLUME_BITMAP              = 0x0009006f   # func 27, method 3
FSCTL_GET_RETRIEVAL_POINTERS         = 0x00090073   # func 28, method 3
FSCTL_MOVE_FILE                      = 0x00090074   # func 29, method 0
FSCTL_LOOKUP_STREAM_FROM_CLUSTER     = 0x000901fc   # func 127, method 0
FSCTL_GET_RETRIEVAL_POINTER_BASE     = 0x00090234   # func 141, method 0
FSCTL_QUERY_FILE_SYSTEM_RECOGNITION  = 0x0009024c   # func 147, method 0

IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS = 0x00560000   # func 0, method 0


# Structures
class DISK_EXTENT(ctypes.Structure):
    _fields_ = [
        ('DiskNumber', ctypes.c_ulong),
        ('StartingOffset', ctypes.c_ulonglong),
        ('ExtentLength', ctypes.c_ulonglong),
    ]

class VOLUME_DISK_EXTENTS(ctypes.Structure):
    _fields_ = [
        ('NumberOfDiskExtents', ctypes.c_ulong),
        ('Extents', DISK_EXTENT * 1),
        # Call to IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS will
        # fail with ERROR_MORE_DATA if more than one extent exists
    ]

class VOLUME_BITMAP_BUFFER(ctypes.Structure):
    _fields_ = [
        ('StartingLcn', ctypes.c_ulonglong),
        ('BitmapSize', ctypes.c_ulonglong),
        # Data buffer follows - array of char, starting at bit 0 of byte 0 for cluster 0
    ]

class LOOKUP_STREAM_FROM_CLUSTER_INPUT(ctypes.Structure):
    _fields_ = [
        ('Flags', ctypes.c_ulong),      # Currently no flags are defined for this operation
        ('NumberOfClusters', ctypes.c_ulong),
        ('Cluster', ctypes.c_ulonglong * 1),            # Len should be >= NumberOfClusters
    ]

class LOOKUP_STREAM_FROM_CLUSTER_OUTPUT(ctypes.Structure):
    _fields_ = [
        ('Offset', ctypes.c_ulong),     # Offset in buffer of first match entry, zero if none
        ('NumberOfMatches', ctypes.c_ulong),
        ('BufferSizeRequired', ctypes.c_ulong),
    ]

class LOOKUP_STREAM_FROM_CLUSTER_ENTRY(ctypes.Structure):
    _fields_ = [
        ('OffsetToNext', ctypes.c_ulong),       # 4
        ('Flags', ctypes.c_ulong),              # 8
        ('Reserved', ctypes.c_ulonglong),       # 16
        ('Cluster', ctypes.c_ulonglong),        # 24
        ('FileName', ctypes.c_wchar * 1),       # Null-terminated wchar string of unspecified length (up to 32k chars)
    ]

class RETRIEVAL_POINTERS_BUFFER(ctypes.Structure):
    _fields_ = [
        ('ExtentCount', ctypes.c_ulong),
        ('StartingVcn', ctypes.c_ulonglong),
        ('NextVcn', ctypes.c_ulonglong),
        ('Lcn', ctypes.c_ulonglong),
        # NextVcn and Lcn repeat for as many entries as ExtentCount
    ]

class MOVE_FILE_DATA(ctypes.Structure):
    _fields_ = [
        ('FileHandle', ctypes.c_void_p),
        ('StartingVcn', ctypes.c_ulonglong),
        ('StartingLcn', ctypes.c_ulonglong),
        ('ClusterCount', ctypes.c_ulong),
    ]

    
# Function arg/return types
ctypes.windll.kernel32.CreateFileW.restype = ctypes.c_void_p    # HANDLE
ctypes.windll.kernel32.CreateFileW.argtypes = [
    c_wchar_p,  # lpFileName
    c_ulong,    # dwDesiredAccess
    c_ulong,    # dwShareMode
    c_void_p,   # lpSecurityAttributes
    c_ulong,    # dwCreationDisposition
    c_ulong,    # dwFlagsAndAttributes
    c_void_p,   # hTemplateFile
]
ctypes.windll.kernel32.SetFilePointerEx.restype = ctypes.c_bool
ctypes.windll.kernel32.SetFilePointerEx.argtypes = [
    c_void_p,               # HANDLE hFile
    c_longlong,             # liDistanceToMove
    POINTER(c_longlong),    # *QWORD lpNewFilePointer
    c_ulong,                # dwMoveMethod
]
ctypes.windll.kernel32.WriteFile.restype = ctypes.c_bool
ctypes.windll.kernel32.WriteFile.argtypes = [
    c_void_p,           # HANDLE hFile
    c_char_p,           # lpBuffer
    c_ulong,            # nNumberOfBytesToWrite
    POINTER(c_ulong),   # lpNumberOfBytesWritten
    c_void_p,           # lpOverlapped
]
ctypes.windll.kernel32.DeviceIoControl.restype = ctypes.c_bool
ctypes.windll.kernel32.DeviceIoControl.argtypes = [
    c_void_p,   # hDevice
    c_ulong,    # dwIoControlCode
    c_void_p,   # lpInBuffer
    c_ulong,    # nInBufferSize
    c_void_p,   # lpOutBuffer
    c_ulong,    # nOutBufferSize
    POINTER(c_ulong),   # lpBytesReturned
    c_void_p,   # lpOverlapped
]
ctypes.windll.kernel32.GetDiskFreeSpaceW.restype = ctypes.c_bool
ctypes.windll.kernel32.GetDiskFreeSpaceW.argtypes = [
    c_wchar_p,          # lpRootPathName
    POINTER(c_ulong),   # lpSectorsPerCluster
    POINTER(c_ulong),   # lpBytesPerSector
    POINTER(c_ulong),   # lpNumberOfFreeClusters
    POINTER(c_ulong),   # lpTotalNumberOfClusters
]
ctypes.windll.kernel32.GetVolumeInformationW.restype = ctypes.c_bool
ctypes.windll.kernel32.GetVolumeInformationW.argtypes = [
    c_wchar_p,          # lpRootPathName
    c_wchar_p,          # lpVolumeNameBuffer
    c_ulong,            # nVolumeNameSize
    POINTER(c_ulong),   # LPDWORD lpVolumeSerialNumber
    POINTER(c_ulong),   # LPDWORD lpMaximumComponentLength
    POINTER(c_ulong),   # LPDWORD lpFileSystemFlags
    c_wchar_p,          # lpFileSystemNameBuffer
    c_ulong,            # nFileSystemNameSize
]