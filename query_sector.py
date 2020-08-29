import ctypes
import logging
import os
import tempfile
import time

from win_types import *

logger = logging.getLogger(__name__)
kernel32 = ctypes.windll.kernel32

def print_error_string_old(code):
    msg_ptr = ctypes.c_wchar_p()
    msg_len = kernel32.FormatMessageW(
        0x1100,     # flags = _FROM_SYSTEM | _ALLOCATE_BUFFER
        None,       # lpSource - ignored for these flags
        code,       # dwMessageId
        0,          # Language ID
        ctypes.byref(msg_ptr),
        0,          # buffer size / minimum size to allocate
        None,
    )
    print(" err %s: %s" % (err, msg_ptr.value))
    res = kernel32.LocalFree(msg_ptr)
    if res:
        logger.error('LocalFree returned nonzero (%s) for ptr %s' % (hex(res), hex(msg_ptr)))

def get_error_string(code):
    msg_buf = ctypes.create_unicode_buffer(256)
    msg_len = kernel32.FormatMessageW(
        0x1000,     # flags = _FROM_SYSTEM
        None,       # lpSource - ignored for these flags
        code,       # dwMessageId
        0,          # Language ID
        msg_buf,
        len(msg_buf),   # buffer size / minimum size to allocate
        None,       # arg list
    )
    return msg_buf.value

def try_read_cluster(volume, cluster, cluster_size):
    """Tries to read from the given cluster of the volume, and returns the result code."""
    print('Testing cluster read... ', end='')
    os.sys.stdout.flush()
    res = kernel32.SetFilePointerEx(
        volume,
        ctypes.c_longlong(cluster * cluster_size),
        None,       # lpNewFilePointer
        0,          # FILE_BEGIN   (_CURRENT = 1, _END = 2)
    )
    if res == 0:
        logger.fatal('Failed to seek to cluster location')
        raise ctypes.WinError()
    buf = ctypes.create_string_buffer(cluster_size)
    out_size = ctypes.c_ulong()
    res = kernel32.ReadFile(
        volume,
        buf,
        ctypes.sizeof(buf),
        ctypes.byref(out_size),
        None,
    )
    if res == 0:
        err = kernel32.GetLastError()
        if err == 23:
            print('failed with CRC error (err 23).')
        else:
            raise ctypes.WinError(err)
    else:
        if out_size.value != cluster_size:
            print('-WARNING - partial read (%s of %s)' % (out_size.value, cluster_size))
        else:
            print('success.')
    return res
    
    
    
def main():
    force_write = False
    if len(os.sys.argv) == 3:
        if os.sys.argv[2] == '--force':
            force_write = True
            del os.sys.argv[2]
    
    if len(os.sys.argv) != 2:
        print("\nUsage: %s <driveletter> [--force]" % os.sys.argv[0])
        print(
"""
  Takes a physical disk sector number (in decimal) and tries to map it
  to the NTFS cluster using that sector and determine what's located
  there. If it's unused, attempt to read from that cluster; if the
  read fails, offer to write dummy data there (to allow a SMART disk
  drive to reallocate the sector).
        
   --force: always offer to overwrite an empty cluster,
            even if it was read successfully.""")
        return
    drive_letter = os.sys.argv[1].upper()
    if len(drive_letter) not in (1, 2):
        print("Drive letter should be in the form 'C' or 'C:'")
        return
    if drive_letter[-1] == ':':
        drive_letter = drive_letter[:-1]
    if drive_letter < 'A' or drive_letter > 'Z':
        print('Drive letter should be in A...Z.')
        return
    vol_name = r'\\.\%s:' % drive_letter
    vol_path = '%s:\\' % drive_letter

    print("Opening %s..." % vol_name)

    volume = kernel32.CreateFileW(
        vol_name,
        2 << 30,    # GENERIC_READ 
        0x3,        # FILE_SHARE_READ | FILE_SHARE_WRITE
        None,       # securitydescriptor
        0x3,        # OPEN_EXISTING
        #0x80000000, # WRITE_THROUGH
        0,
        None,       # hTemplateFile
    )
    if volume == INVALID_HANDLE:
        logger.fatal('Failed to open a handle to the volume. Do you have admin privileges?')
        raise ctypes.WinError()
    logger.info("Volume handle: %s" % volume)

    # 0x00090028  FSCTL_IS_VOLUME_MOUNTED
    out_size = ctypes.c_ulong()
    res = kernel32.DeviceIoControl(
        volume,
        FSCTL_IS_VOLUME_MOUNTED,
        None,
        0,
        None,
        0,
        ctypes.byref(out_size),        # lpBytesReturned - don't care (is 0)
        None,           # lpOverlapped
    )
    err = kernel32.GetLastError()
    if err != 0:
        print(" Error %s checking volume mount status: %s" % (err, get_error_string(err)))
        return
    print(" Volume is%s mounted" % ('' if res else ' not'))

    # Get physical info
    vde = VOLUME_DISK_EXTENTS()
    res = kernel32.DeviceIoControl(
        volume,
        IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS,
        None,                   # lpInputBuffer
        0,
        ctypes.byref(vde),
        ctypes.sizeof(vde),     # out buffer size
        ctypes.byref(out_size), # lpBytesReturned
        None,                   # lpOverlapped
    )
    if res == 0:
        err = kernel32.GetLastError()
        if err == 234:  # ERR_MORE_DATA
            print(" Multiple extents: Windows reports %s extents for this volume." % vde.NumberOfDiskExtents)
            print(" We don't support more than one extent yet!")
        else:
            logger.fatal("Failed to get volume's on-disk location")
            raise ctypes.WinError(err)
        return
    assert vde.NumberOfDiskExtents == 1, "Did not get exactly one extent back, despite error check?"
    print(" Volume is located on \\\\.\\PhysicalDisk%s" % vde.Extents[0].DiskNumber)
    print("  %s bytes starting at disk offset %s" % (vde.Extents[0].ExtentLength, vde.Extents[0].StartingOffset))
    vol_start = vde.Extents[0].StartingOffset
    vol_end = vol_start + vde.Extents[0].ExtentLength       # This is the first byte offset AFTER the end of the volume

    # Find cluster size
    spc = ctypes.c_ulong()
    bps = ctypes.c_ulong()
    cfree = ctypes.c_ulong()
    ctotal = ctypes.c_ulong()
    res = kernel32.GetDiskFreeSpaceW(
        vol_path,
        ctypes.byref(spc),      # Sectors per Cluster
        ctypes.byref(bps),      # Bytes / sector
        ctypes.byref(cfree),    # free clusters
        ctypes.byref(ctotal),   # Total clusters
    )
    if res == 0:
        err = kernel32.GetLastError()
        print(" Error %s: %s" % (err, get_error_string(err)))
        return
    bps = bps.value     # We'll use this later
    cluster_size = bps * spc.value
    print("  %s bytes per sector, %s sectors per cluster (%s bytes per cluster)"
          % (bps, spc.value, cluster_size))

    # Verify that it's NTFS
    fs_flags = ctypes.c_uint()
    buf = ctypes.create_unicode_buffer(32)    # FS type name buffer
    res = kernel32.GetVolumeInformationW(
        vol_path,
        None,       # lpVolNameBuffer
        0,          # nVolNameSize
        None,       # lpVolSerial
        ctypes.byref(out_size),     # max path component length, but we don't care
        ctypes.byref(fs_flags),
        buf,
        ctypes.sizeof(buf),
    )
    if res == 0:
        logger.fatal('Error calling GetVolumeInformation')
        raise ctypes.WinError()
    if fs_flags.value & 0x80000:
        logger.warning('Volume is read-only')
    if buf.value != 'NTFS':
        logger.fatal('Only tested on NTFS -- FS type is "%s"' % buf.value)
        return

    # Verify starting cluster offset
    buf = ctypes.c_ulonglong()
    res = kernel32.DeviceIoControl(
        volume,
        FSCTL_GET_RETRIEVAL_POINTER_BASE,
        None,
        0,
        ctypes.byref(buf),
        ctypes.sizeof(buf),
        ctypes.byref(out_size),     # lpBytesReturned
        None,                       # lpOverlapped
    )
    if res == 0:
        logger.fatal('Failure when requesting FS starting cluster')
        raise ctypes.WinError()
    if buf.value != 0:
        raise RuntimeError('First cluster offset in volume is not zero (got %s instead)' % buf.value)

    # Try to get volume bitmap size
    buf = ctypes.create_string_buffer(32)       # Doesn't seem to like having just a 16-byte buffer, even though in theory that's enough for header
    res = kernel32.DeviceIoControl(
        volume,
        FSCTL_GET_VOLUME_BITMAP,
        ctypes.byref(ctypes.c_ulonglong(0)),        # lpInputBuffer - struct of one LARGE_INTEGER for starting LCN
        8,
        buf,
        ctypes.sizeof(buf),         # out buffer size
        ctypes.byref(out_size),     # lpBytesReturned
        None,                       # lpOverlapped
    )
    if res != 0:
        print("Unexpected success from GET_VOLUME_BITMAP with no output buffer! Aborting.")
        return
    err = kernel32.GetLastError()
    if err == 122:      #  ERROR_INSUFFICIENT_BUFFER
        print(" GET_VOLUME_BITMAP reported buffer is too small, required size not known. Aborting.")
        return
    if err != 234:      # ERROR_MORE_DATA_AVAILABLE is expected
        logger.fatal('Failed to get size of volume bitmap')
        raise ctypes.WinError(err)
    header = VOLUME_BITMAP_BUFFER.from_buffer(buf)
    if header.BitmapSize == 0:
        print(" Error: GET_VOLUME_BITMAP result shows bitmap size is zero? Aborting.")

    bm_buf = ctypes.create_string_buffer(33 + header.BitmapSize // 8)
    print("Loading volume bitmap (%s bytes)..." % ctypes.sizeof(bm_buf))
    res = kernel32.DeviceIoControl(
        volume,
        FSCTL_GET_VOLUME_BITMAP,
        ctypes.byref(ctypes.c_ulonglong(0)),    # lpInputBuffer
        8,
        bm_buf,
        ctypes.sizeof(bm_buf),  # out buffer size
        ctypes.byref(out_size), # lpBytesReturned
        None,                   # lpOverlapped
    )
    if res == 0:
        raise ctypes.WinError()
    print('Successfully loaded bitmap.\n')

    query = input('Enter disk sector to query: ')
    try:
        query = int(query)
    except ValueError:
        print("Not a valid integer.")
        return

    offset = query * bps
    if offset < vol_start or offset >= vol_end:
        print('Sector is not part of this volume.')
        return
    cluster = (offset - vol_start) // cluster_size
    print('Sector is in cluster %s of volume.' % cluster)
    bm_byte = bm_buf[16 + cluster // 8]
    # If set in bitmap...
    if ord(bm_byte) & 2**(cluster % 8):
        print('Cluster is in use. Querying for file...')
        lookup_in = LOOKUP_STREAM_FROM_CLUSTER_INPUT()
        lookup_in.NumberOfClusters = 1
        lookup_in.Cluster[0] = cluster
        buf = ctypes.create_string_buffer(70000)        # File name may be up to 64k bytes
        res = kernel32.DeviceIoControl(
            volume,
            FSCTL_LOOKUP_STREAM_FROM_CLUSTER,
            ctypes.byref(lookup_in),
            ctypes.sizeof(lookup_in),
            buf,
            ctypes.sizeof(buf),
            ctypes.byref(out_size),
            None,
        )
        if res == 0:
            err = kernel32.GetLastError()
            if err == 234:
                logger.warning('Got more file matches than will fit in buffer! Some results will not be shown')
            else:
                raise ctypes.WinError(err)
        lookup_output = LOOKUP_STREAM_FROM_CLUSTER_OUTPUT.from_buffer(buf)
        if lookup_output.NumberOfMatches == 0:
            print("Didn't find any files using that cluster - probably a bug in the volume bitmap handling?")
            return
        elif lookup_output.NumberOfMatches > 1:
            print("Unexpectedly got more than one result for files using this cluster!")
        print("File results for this cluster:")
        offs = lookup_output.Offset
        while True:
            stream_entry = LOOKUP_STREAM_FROM_CLUSTER_ENTRY.from_buffer(buf, offs)
            print('    ', end='')
            if stream_entry.Flags & 1: print('*PF ', end='')    # In pagefile
            if stream_entry.Flags & 2: print('*DD ', end='')    # Defrag denied
            if stream_entry.Flags & 12: print('*SYS ', end='')  # FS system or TxF system
            attrs = (stream_entry.Flags >> 24) & 3
            if attrs == 1: pass     # $DATA stream
            if attrs == 2: print('*IDX ', end='')   # $INDEX_ALLOCATION attribute
            if attrs == 3: print('*ADS ', end='')   # Some other attribute
            print(ctypes.wstring_at(ctypes.byref(stream_entry, 24)))
            if stream_entry.OffsetToNext == 0: break
            offs += stream_entry.OffsetToNext
        _ = try_read_cluster(volume, cluster, cluster_size)
        return

    # Not set in bitmap
    print('Cluster is not in use.')
    res = try_read_cluster(volume, cluster, cluster_size)
    if res != 0 and not force_write:
        print('Done.')
        return

    res = input('Try to rewrite that cluster with dummy data (y/n)? ')
    if not res.upper().startswith('Y'):
        return

    tmp_file_name = vol_path + '__dummy_.tmp'
    handle = kernel32.CreateFileW(
        tmp_file_name,
        3 << 30,        # GENERIC_READ | GENERIC_WRITE
        0,              # Don't share
        None,
        2,              # CREATE_ALWAYS
        0x84000000,     # FILE_FLAG_WRITE_THROUGH | _DELETE_ON_CLOSE
        None,           # hTemplate
    )
    if handle == INVALID_HANDLE:
        logger.fatal('Error creating temp file')
        raise ctypes.WinError()
    res = kernel32.WriteFile(
        handle,
        b'.' * cluster_size,
        cluster_size,
        ctypes.byref(out_size),
        None,
    )
    if res == 0:
        logger.fatal('Error writing to temp file')
        raise ctypes.WinError()

    rpb = RETRIEVAL_POINTERS_BUFFER()
    res = kernel32.DeviceIoControl(
        handle,
        FSCTL_GET_RETRIEVAL_POINTERS,
        ctypes.byref(ctypes.c_ulonglong(0)),
        8,
        ctypes.byref(rpb),
        ctypes.sizeof(rpb),
        ctypes.byref(out_size),
        None,
    )
    if res == 0:
        logger.fatal('Could not retrieve temp file allocation data')
        raise ctypes.WinError()
    logger.debug('Retrieval pointers: %s extent(s) starting at VCN %s:' % (rpb.ExtentCount, rpb.StartingVcn))
    logger.debug(' 1- %s VCs at %s' % (rpb.NextVcn - rpb.StartingVcn, rpb.Lcn))
    assert rpb.ExtentCount == 1 and rpb.NextVcn - rpb.StartingVcn == 1, 'Dummy file too big?'
    if rpb.Lcn != cluster:
        mfd = MOVE_FILE_DATA(
            FileHandle=handle,
            StartingVcn=0,
            StartingLcn=cluster,
            ClusterCount=1,
        )
        res = kernel32.DeviceIoControl(
            volume,
            FSCTL_MOVE_FILE,
            ctypes.byref(mfd),
            ctypes.sizeof(mfd),
            None,
            0,
            ctypes.byref(out_size),
            None,
        )
        if res == 0:
            logger.fatal('Failed to move temp file to target cluster')
            raise ctypes.WinError()

    res = kernel32.CloseHandle(handle)
    if res == 0:
        logger.fatal('Error closing temp file')
        raise ctypes.WinError()
    res = kernel32.CloseHandle(volume)
    if res == 0:
        logger.fatal('Error closing volume handle')
        raise ctypes.WinError()

    print("Done!\n")

if __name__ == '__main__':
    main()
