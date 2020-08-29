# query_sector
Small Windows utility for disk-sector diagnosis.

Uses windows APIs to translate a raw disk sector number to the cluster number
within the filesystem, identify what (if anything) is stored there, then
tests whether the cluster can be read, and if there is
a read error and the cluster is unusued, offers to write a dummy file to that
location (intended to trigger the drive's internal reallocation routines).


# Usage

Install Python from the Windows store or from python.org.

Go to the appropriate directory, and run:
`python query_sector.py <driveletter>`

Enter the sector number to query.


# Known limitation

- Refuses to run on anything other than NTFS, because that's the only thing I have tested it on
- Does not support volumes with multiple extents (eg Windows RAID volumes)
- Target volume must be mounted with a drive letter
- Can't do anything with sectors that are outside any Windows partition
- Can't always write a file to the cluster, if it's in Windows 'reserved free space'


# NO WARRANTY

Since this program uses Windows deframentation APIs to allocate a file
to the cluster in question, there should in theory be no risk of any
data loss. Nonetheless, there is NO WARRANTY for this software, and I am
not responsible if anything goes wrong. If you are at all in doubt, you 
should consult an expert to give you advice on your specific situation.
