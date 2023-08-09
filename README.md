# python3-ovirt-to-proxmox
Python script to migrate VMs from oVirt to Proxmox. Use with care!!

Prerequisites:
* apt install python3-pip libxml2-dev
* pip install requests pyyaml proxmoxer requests ovirt-engine-sdk-python

How to use:
1. Mount oVirt NFS storage locally on Proxmox node.
   * mkdir -p /media/nfs/STORAGE_DOMAIN
   * mount -o ro 1.2.3.4:/mnt/STORAGE_DOMAIN /media/nfs/STORAGE_DOMAIN

3. Adjust settings in settings.yaml
   * Set "storage" to destination storage on proxmox node.
   * Set "nfs_base_dir" to local NFS mount on node
   * Set "node" to excact name of the node.

5. Script execution examples
   * Move VM with exact match. Execute "python3 ovirt_to_proxmox.py --vmname MYVM"
   * Move VMs based on name pattern and wildcard. Execute "python3 ovirt_to_proxmox.py --vmname MYVM*"
   * Move all VMs with wildcard, catch all. Execute "python3 ovirt_to_proxmox.py --vmname *"
