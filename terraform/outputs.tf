# Output para obter o IP público da VM
output "public_ip" {
  description = "IP Público da instância VM para acesso SSH e testes"
  value       = oci_core_instance.rag_vm.public_ip
}