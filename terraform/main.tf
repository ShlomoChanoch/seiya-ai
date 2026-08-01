# ------------------------------------------------------------------------------
# NETWORKING (VCN, IGW, Route Table, Security List, Subnet)
# ------------------------------------------------------------------------------

resource "oci_core_vcn" "rag_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.0.0.0/16"]
  display_name   = "rag-deepseek-vcn"
  dns_label      = "ragvcn"
}

resource "oci_core_internet_gateway" "rag_igw" {
  compartment_id = var.compartment_ocid
  display_name   = "rag-internet-gateway"
  vcn_id         = oci_core_vcn.rag_vcn.id
  enabled        = true
}

resource "oci_core_route_table" "rag_public_rt" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.rag_vcn.id
  display_name   = "rag-public-route-table"

  route_rules {
    description       = "outbound traffic to internet"
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.rag_igw.id
  }
}

resource "oci_core_security_list" "rag_security_list" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.rag_vcn.id
  display_name   = "rag-security-list"

  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
  }

  # SSH
  ingress_security_rules {
    protocol  = "6"
    source    = "0.0.0.0/0"
    stateless = false
    tcp_options {
      min = 22
      max = 22
    }
  }
}

resource "oci_core_subnet" "rag_public_subnet" {
  compartment_id    = var.compartment_ocid
  vcn_id            = oci_core_vcn.rag_vcn.id
  cidr_block        = "10.0.1.0/24"
  display_name      = "rag-public-subnet"
  dns_label         = "ragsub"
  route_table_id    = oci_core_route_table.rag_public_rt.id
  security_list_ids = [oci_core_security_list.rag_security_list.id]
}

# ------------------------------------------------------------------------------
# COMPUTE INSTANCE (VM.Standard.E4.Flex)
# ------------------------------------------------------------------------------

# Busca pela imagem oficial do Ubuntu 22.04 LTS
data "oci_core_images" "ubuntu" {
  compartment_id           = var.compartment_ocid
  operating_system         = "Canonical Ubuntu"
  operating_system_version = "22.04"
  shape                    = "VM.Standard.E4.Flex"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

resource "oci_core_instance" "rag_vm" {
  compartment_id      = var.compartment_ocid
  availability_domain = var.availability_domain
  display_name        = "deepseek-rag-server"
  shape               = "VM.Standard.E4.Flex"

  # Configuração Flex: 2 OCPUs (4 vCPUs) e 16 GB de RAM
  shape_config {
    ocpus         = 2
    memory_in_gbs = 16
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.rag_public_subnet.id
    assign_public_ip = true
    display_name     = "rag-vnic"
  }

  source_details {
    source_type             = "image"
    source_id               = data.oci_core_images.ubuntu.images[0].id
    boot_volume_size_in_gbs = 80
  }

  metadata = {
    ssh_authorized_keys = file(var.ssh_public_key_path)

    # Script de inicialização automática (Cloud-Init)
    user_data = base64encode(<<-EOF
      #!/bin/bash
      apt-get update -y
      apt-get install -y python3-pip python3-venv git curl build-essential

      # Instalação do Ollama
      curl -fsSL https://ollama.com/install.sh | sh

      # Inicialização do serviço Ollama e download do modelo DeepSeek-R1:1.5b
      systemctl enable ollama
      systemctl start ollama
      sleep 5
      ollama pull deepseek-r1:1.5b

      # Configuração de firewall nativo do Ubuntu (iptables/ufw da OCI)
      iptables -F
      netfilter-persistent save
    EOF
    )
  }
}