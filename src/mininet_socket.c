#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/un.h>

#include "constants.h"
#include "utils.h"

#include "mininet_socket.h"

#define SOCKET_PATH_MAIN "/tmp/mini_savi_main.sock"

static int sockfd = -1;
static struct sockaddr_un socket_addr;

static unsigned int
mininet_socket_send_impl(const char *message, size_t length)
{
  ssize_t sent;

  if (!message || length == 0 || sockfd < 0) {
    return FALSE;
  }

  sent = sendto(sockfd, message, length, 0,
		(const struct sockaddr *) &socket_addr, sizeof(socket_addr));
  if (sent < 0 || (size_t) sent != length) {
    error("mininet socket send failed. Disabling mininet integration.");
    mininet_socket_cleanup();
    return FALSE;
  }

  return TRUE;
}

unsigned int
mininet_socket_init(void)
{
  if (sockfd >= 0) {
    return TRUE;
  }

  sockfd = socket(AF_UNIX, SOCK_DGRAM, 0);
  if (sockfd < 0) {
    error("create Unix socket for mininet link info failed! Running in standalone mode.");
    return FALSE;
  }

  memset(&socket_addr, 0, sizeof(socket_addr));
  socket_addr.sun_family = AF_UNIX;
  strncpy(socket_addr.sun_path, SOCKET_PATH_MAIN,
	  sizeof(socket_addr.sun_path) - 1);

  fprintf(stderr, "Unix socket created for mininet integration (path: %s)\n",
	  SOCKET_PATH_MAIN);
  return TRUE;
}

void
mininet_socket_cleanup(void)
{
  if (sockfd >= 0) {
    close(sockfd);
    sockfd = -1;
  }
}

unsigned int
mininet_socket_is_available(void)
{
  return (sockfd >= 0);
}

unsigned int
mininet_socket_send(const char *message)
{
  if (!message) {
    return FALSE;
  }

  return mininet_socket_send_impl(message, strlen(message));
}

unsigned int
mininet_socket_send_n(const char *message, size_t length)
{
  return mininet_socket_send_impl(message, length);
}
