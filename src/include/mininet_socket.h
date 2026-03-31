#ifndef _MININET_SOCKET_H_
#define _MININET_SOCKET_H_

#include <stddef.h>

unsigned int mininet_socket_init(void);
void mininet_socket_cleanup(void);
unsigned int mininet_socket_is_available(void);
unsigned int mininet_socket_send(const char *message);
unsigned int mininet_socket_send_n(const char *message, size_t length);

#endif
/* !_MININET_SOCKET_H_ */
