#!/usr/bin/python3
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from proxmoxer import ProxmoxAPI
from proxmoxer.tools import Tasks
import ovirtsdk4 as sdk
import ovirtsdk4.types as types
import argparse
import json
import time
import yaml

def ovirt_api():
    ovirt_api = sdk.Connection(
        url=settings['ovirt']['engine_url'],
        username=settings['ovirt']['username'],
        password=settings['ovirt']['password'],
        ca_file=settings['ovirt']['cert'],
    )

    return(ovirt_api)

def proxmox_api():
    proxmox_api = ProxmoxAPI(
        settings['proxmox']['ip'],
        user=settings['proxmox']['username'],
        password=settings['proxmox']['password'],
        verify_ssl=False
    )

    return(proxmox_api)

def bytesto(bytes, to, bsize=1024):
    a = {'k' : 1, 'm': 2, 'g' : 3, 't' : 4, 'p' : 5, 'e' : 6 }
    r = float(bytes)

    return bytes / (bsize ** a[to])

def ovirt_shutdown_vm(vmid):
    vm_service = vms_service.vm_service(vmid)
    vm_service.shutdown()
    while True:
        time.sleep(5)
        vm = vm_service.get()
        if vm.status == types.VmStatus.DOWN:
            break

def get_all_vnics():
    profiles_service = ovirt_api.system_service().vnic_profiles_service()
    vnic_name_id = {}
    for profile in profiles_service.list():
        vnic_name_id[profile.id] = profile.id
        vnic_name_id[profile.id] = profile.name

    return (vnic_name_id)

def get_vm_nics_by_vmid(vmid):
    nics_service = vms_service.vm_service(vmid).nics_service()
    nics_dict = {}
    for nic in nics_service.list():
        nics_dict[nic.vnic_profile.id] = nic.mac.address

    return(nics_dict)

def get_vm_disks_by_vmid(vmid):
    disks_service = vms_service.vm_service(vmid).disk_attachments_service()
    image_service = ovirt_api.system_service().disks_service()
    disks_dict = {}
    for disk in disks_service.list():
        storage_domain_id = ovirt_api.system_service().disks_service().disk_service(disk.id).get().storage_domains[0].id
        storage_domain_name = ovirt_api.system_service().storage_domains_service().storage_domain_service(storage_domain_id).get().name
        disks_dict[disk.id] = {}
        disks_dict[disk.id]['domain_id'] = storage_domain_id
        disks_dict[disk.id]['storage'] = storage_domain_name
        disks_dict[disk.id]['disk_id'] = disk.id
        disks_dict[disk.id]['image_id'] = image_service.disk_service(disk.id).get().image_id

    return(disks_dict)

def get_vm_configuration(vm_name):
    virtual_machines = vms_service.list(search=f"status=up name={vm_name}")
    vm_list_dict = {}
    for VM in virtual_machines:
        vm_list_dict[VM.name] = {}
        vm_list_dict[VM.name]['name'] = VM.name
        vm_list_dict[VM.name]['id'] = VM.id
        vm_list_dict[VM.name]['memory'] = int(bytesto(VM.memory,'m'))
        vm_list_dict[VM.name]['cpu'] = 'x86-64-v3' if VM.cpu.mode == None else 'host'
        vm_list_dict[VM.name]['sockets'] = VM.cpu.topology.sockets
        vm_list_dict[VM.name]['cores'] = VM.cpu.topology.cores
        vm_list_dict[VM.name]['disks'] = {}
        vm_list_dict[VM.name]['nics'] = {}

        for nic, mac in get_vm_nics_by_vmid(VM.id).items():
            vm_list_dict[VM.name]['nics'][mac] = get_all_vnics[nic]

        for disk, image in get_vm_disks_by_vmid(VM.id).items():
            vm_list_dict[VM.name]['disks'][disk] = image

    return(vm_list_dict)

def create_vm(ovirt_vms_dict):
    node = proxmox_api.nodes(settings["proxmox"]["node"])
    for vm_index, vm in enumerate(ovirt_vms_dict.values()):
        ovirt_shutdown_vm(vm['id'])
        vmid = proxmox_api.cluster.nextid.get()
        vm_cfg = {
            'vmid' : vmid,
            'name' : vm['name'],
            'memory' : vm['memory'],
            'cpu' : vm['cpu'],
            'machine': 'q35',
            'agent': 1,
            'cores': vm['cores'],
            'sockets': vm['sockets'],
            'ostype': 'l26',
            'ide2': 'none,media=cdrom',
            'scsihw': 'virtio-scsi-single',
            'hotplug': 1,
            'tablet': 1,
            'vga': 'qxl',
            'start': '0'
        }

        if vm['nics']:
            for nic_index, nic_vlan in enumerate(vm['nics'].items()):
                vm_cfg[f'net{nic_index}'] = f'virtio,bridge=vmbr1,macaddr={nic_vlan[0]},tag={nic_vlan[1].strip("vlan")}'

        if vm['disks']:
            for disk_index, (disk, disk_details) in enumerate(vm['disks'].items()):
                vm_cfg[f'scsi{disk_index}'] = f'{settings["proxmox"]["storage"]}:0,import-from={settings["proxmox"]["nfs_base_dir"]}/{disk_details["storage"]}/{disk_details["domain_id"]}/images/{disk_details["disk_id"]}/{disk_details["image_id"]},media=disk,format=qcow2,discard=on,ssd=1,iothread=1'

        print(json.dumps(vm_cfg, indent=4))
        task_id = getattr(node, 'qemu').create(**vm_cfg)
        task_status = node.tasks(task_id).status.get()

        while task_status['status'] == 'running':
            task_status = node.tasks(task_id).status.get()
            print(f"Task status: {task_status['status']}")
            time.sleep(3)

if __name__ == '__main__':
    # Args
    cli_args = argparse.ArgumentParser(description='oVirt to Proxmox VM migration')
    cli_args.add_argument('--vmname', action="store", type=str, dest="vm_name", required=True, help="VM name in oVirt enviroment. Can be used with wildcard, ex MYVM* or * to move all vms")
    cli_args = cli_args.parse_args()

    # Load settings and credentials from yaml, initiate APIs to both platforms
    settings = yaml.safe_load(open('settings.yaml', 'r'))
    proxmox_api = proxmox_api()
    ovirt_api = ovirt_api()

    # oVirt service
    vms_service = ovirt_api.system_service().vms_service()

    # Get all vnics to be used later
    get_all_vnics = get_all_vnics()

    # Get all VM configurations and insert to dict
    ovirt_vms_dict = get_vm_configuration(cli_args.vm_name)

    # Create VM on Proxmox and shutdown on oVirt
    create_vm(ovirt_vms_dict)
