/*
 * Description :  Xilinx Virtual Cable Server for Raspberry Pi (Modern Version)
 *                Updated for Raspberry Pi 5 with libgpiod
 *
 * See Licensing information at End of File.
 */

#include <fcntl.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <netinet/tcp.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <signal.h>
#include <time.h>
#include <gpiod.h>
#include <errno.h>

/* GPIO numbers for each signal. Negative values are invalid */
static int tck_gpio = 11;
static int tms_gpio = 25;
static int tdi_gpio = 10;
static int tdo_gpio = 9;
// static int tck_gpio = 6;
// static int tms_gpio = 13;
// static int tdi_gpio = 19;
// static int tdo_gpio = 26;

static int verbose = 0;
static int port = 2542;  // Default port number

/* GPIO chip and line handles */
static struct gpiod_chip *chip = NULL;
static struct gpiod_line *tck_line = NULL;
static struct gpiod_line *tms_line = NULL;
static struct gpiod_line *tdi_line = NULL;
static struct gpiod_line *tdo_line = NULL;

/* Transition delay coefficients */
#define JTAG_DELAY (40)
static unsigned int jtag_delay = JTAG_DELAY;

static int bcm2835gpio_read(void)
{
   int val = gpiod_line_get_value(tdo_line);
   return val < 0 ? 0 : val;
}

static void bcm2835gpio_write(int tck, int tms, int tdi)
{
   gpiod_line_set_value(tck_line, tck);
   gpiod_line_set_value(tms_line, tms);
   gpiod_line_set_value(tdi_line, tdi);

   for (unsigned int i = 0; i < jtag_delay; i++)
      asm volatile ("");
}

static uint32_t bcm2835gpio_xfer(int n, uint32_t tms, uint32_t tdi)
{
   uint32_t tdo = 0;

   for (int i = 0; i < n; i++) {
      bcm2835gpio_write(0, tms & 1, tdi & 1);
      bcm2835gpio_write(1, tms & 1, tdi & 1);
      tdo |= bcm2835gpio_read() << i;
      tms >>= 1;
      tdi >>= 1;
   }
   return tdo;
}

static bool bcm2835gpio_init(void)
{
   // Open GPIO chip
   chip = gpiod_chip_open_by_name("gpiochip0");
   if (!chip) {
      perror("Failed to open GPIO chip");
      return false;
   }

   if (verbose) {
      printf("GPIO chip opened successfully\n");
   }

   // Get GPIO lines
   tck_line = gpiod_chip_get_line(chip, tck_gpio);
   tms_line = gpiod_chip_get_line(chip, tms_gpio);
   tdi_line = gpiod_chip_get_line(chip, tdi_gpio);
   tdo_line = gpiod_chip_get_line(chip, tdo_gpio);

   if (!tck_line || !tms_line || !tdi_line || !tdo_line) {
      perror("Failed to get GPIO lines");
      return false;
   }

   // Configure TDO as input
   if (gpiod_line_request_input(tdo_line, "xvcpi-tdo") < 0) {
      perror("Failed to configure TDO as input");
      return false;
   }

   // Configure TDI, TCK, TMS as outputs
   if (gpiod_line_request_output(tdi_line, "xvcpi-tdi", 0) < 0) {
      perror("Failed to configure TDI as output");
      return false;
   }

   if (gpiod_line_request_output(tck_line, "xvcpi-tck", 0) < 0) {
      perror("Failed to configure TCK as output");
      return false;
   }

   if (gpiod_line_request_output(tms_line, "xvcpi-tms", 1) < 0) {
      perror("Failed to configure TMS as output");
      return false;
   }

   if (verbose) {
      printf("GPIO lines configured successfully\n");
      printf("TMS=GPIO%d, TDI=GPIO%d, TCK=GPIO%d, TDO=GPIO%d\n", 
             tms_gpio, tdi_gpio, tck_gpio, tdo_gpio);
   }

   // Initialize JTAG state
   bcm2835gpio_write(0, 1, 0);

   return true;
}

static volatile sig_atomic_t running = 1;

static void signal_handler(int sig)
{
   running = 0;
   if (verbose) {
      printf("\nReceived signal %d, shutting down...\n", sig);
   }
}

static void bcm2835gpio_cleanup(void)
{
   if (chip) {
      gpiod_chip_close(chip);
      chip = NULL;
   }
}

static int sread(int fd, void *target, int len) {
   unsigned char *t = target;
   while (len) {
      int r = read(fd, t, len);
      if (r <= 0) {
         if (r == 0) {
            // Connection closed by client
            return 0;
         }
         if (errno == EINTR) {
            // Interrupted by signal, check if we should continue
            if (!running) {
               return -1;  // Signal to exit
            }
            continue;  // Retry the read
         }
         return r;  // Other error
      }
      t += r;
      len -= r;
   }
   return 1;
}

int handle_data(int fd) {
   const char xvcInfo[] = "xvcServer_v1.0:2048\n";

   do {
      // Check if we should exit due to signal
      if (!running) {
         return -1;
      }

      char cmd[16];
      unsigned char buffer[2048], result[1024];
      memset(cmd, 0, 16);

      int read_result = sread(fd, cmd, 2);
      if (read_result != 1) {
         if (read_result == -1) {
            return -1;  // Signal to exit
         }
         return 1;
      }

      if (memcmp(cmd, "ge", 2) == 0) {
         int read_result = sread(fd, cmd, 6);
         if (read_result != 1) {
            if (read_result == -1) return -1;
            return 1;
         }
         memcpy(result, xvcInfo, strlen(xvcInfo));
         if (write(fd, result, strlen(xvcInfo)) != strlen(xvcInfo)) {
            perror("write");
            return 1;
         }
         if (verbose) {
            printf("%u : Received command: 'getinfo'\n", (int)time(NULL));
            printf("\t Replied with %s\n", xvcInfo);
         }
         break;
      } else if (memcmp(cmd, "se", 2) == 0) {
         int read_result = sread(fd, cmd, 9);
         if (read_result != 1) {
            if (read_result == -1) return -1;
            return 1;
         }
         memcpy(result, cmd + 5, 4);
         if (write(fd, result, 4) != 4) {
            perror("write");
            return 1;
         }
         if (verbose) {
            printf("%u : Received command: 'settck'\n", (int)time(NULL));
            printf("\t Replied with '%.*s'\n\n", 4, cmd + 5);
         }
         break;
      } else if (memcmp(cmd, "sh", 2) == 0) {
         int read_result = sread(fd, cmd, 4);
         if (read_result != 1) {
            if (read_result == -1) return -1;
            return 1;
         }
         if (verbose) {
            printf("%u : Received command: 'shift'\n", (int)time(NULL));
         }
      } else {
         fprintf(stderr, "invalid cmd '%s'\n", cmd);
         return 1;
      }

      // For shift command, continue to read length and data
      int len;
      read_result = sread(fd, &len, 4);
      if (read_result != 1) {
         if (read_result == -1) return -1;
         fprintf(stderr, "reading length failed\n");
         return 1;
      }

      size_t nr_bytes = (len + 7) / 8;
      if (nr_bytes * 2 > sizeof(buffer)) {
         fprintf(stderr, "buffer size exceeded\n");
         return 1;
      }

      read_result = sread(fd, buffer, nr_bytes * 2);
      if (read_result != 1) {
         if (read_result == -1) return -1;
         fprintf(stderr, "reading data failed\n");
         return 1;
      }
      memset(result, 0, nr_bytes);

      if (verbose) {
         printf("\tNumber of Bits  : %d\n", len);
         printf("\tNumber of Bytes : %zu \n", nr_bytes);
         printf("\n");
      }

      bcm2835gpio_write(0, 1, 1);

      size_t bytesLeft = nr_bytes;
      int bitsLeft = len;
      size_t byteIndex = 0;
      uint32_t tdi, tms, tdo;

      while (bytesLeft > 0) {
         tms = 0;
         tdi = 0;
         tdo = 0;
         if (bytesLeft >= 4) {
            memcpy(&tms, &buffer[byteIndex], 4);
            memcpy(&tdi, &buffer[byteIndex + nr_bytes], 4);

            tdo = bcm2835gpio_xfer(32, tms, tdi);
            memcpy(&result[byteIndex], &tdo, 4);

            bytesLeft -= 4;
            bitsLeft -= 32;
            byteIndex += 4;

            if (verbose) {
               printf("LEN : 0x%08x\n", 32);
               printf("TMS : 0x%08x\n", tms);
               printf("TDI : 0x%08x\n", tdi);
               printf("TDO : 0x%08x\n", tdo);
            }

         } else {
            memcpy(&tms, &buffer[byteIndex], bytesLeft);
            memcpy(&tdi, &buffer[byteIndex + nr_bytes], bytesLeft);

            tdo = bcm2835gpio_xfer(bitsLeft, tms, tdi);
            memcpy(&result[byteIndex], &tdo, bytesLeft);

            bytesLeft = 0;

            if (verbose) {
               printf("LEN : 0x%08x\n", bitsLeft);
               printf("TMS : 0x%08x\n", tms);
               printf("TDI : 0x%08x\n", tdi);
               printf("TDO : 0x%08x\n", tdo);
            }
            break;
         }
      }

      bcm2835gpio_write(0, 1, 0);

      if (write(fd, result, nr_bytes) != (ssize_t)nr_bytes) {
         perror("write");
         return 1;
      }

   } while (1);
   
   return 0;
}

int main(int argc, char **argv) {
   int i;
   int s;
   int c;

   struct sockaddr_in address;

   opterr = 0;

   while ((c = getopt(argc, argv, "vd:p:c:m:i:o:")) != -1) {
      switch (c) {
      case 'v':
         verbose = 1;
         break;
      case 'd':
         jtag_delay = atoi(optarg);
         if (jtag_delay <= 0)
             jtag_delay = JTAG_DELAY;
         break;
      case 'p':
         port = atoi(optarg);
         if (port <= 0)
             port = 2542; // Default to 2542 if invalid
         break;
      case 'c':
         tck_gpio = atoi(optarg);
         if (tck_gpio < 0)
             tck_gpio = 11; // Default to 11 if invalid
         break;
      case 'm':
         tms_gpio = atoi(optarg);
         if (tms_gpio < 0)
             tms_gpio = 25; // Default to 25 if invalid
         break;
      case 'i':
         tdi_gpio = atoi(optarg);
         if (tdi_gpio < 0)
             tdi_gpio = 10; // Default to 10 if invalid
         break;
      case 'o':
         tdo_gpio = atoi(optarg);
         if (tdo_gpio < 0)
             tdo_gpio = 9; // Default to 9 if invalid
         break;
      case '?':
         fprintf(stderr, "usage: %s [-v] [-d delay] [-p port] [-c tck_pin] [-m tms_pin] [-i tdi_pin] [-o tdo_pin]\n", *argv);
         fprintf(stderr, "  -v          : verbose output\n");
         fprintf(stderr, "  -d delay    : JTAG delay (default: %d)\n", JTAG_DELAY);
         fprintf(stderr, "  -p port     : TCP port (default: %d)\n", 2542);
         fprintf(stderr, "  -c pin      : TCK GPIO pin (default: %d)\n", 11);
         fprintf(stderr, "  -m pin      : TMS GPIO pin (default: %d)\n", 25);
         fprintf(stderr, "  -i pin      : TDI GPIO pin (default: %d)\n", 10);
         fprintf(stderr, "  -o pin      : TDO GPIO pin (default: %d)\n", 9);
         return 1;
      }
   }
   
   if (verbose)
      printf("jtag_delay=%d\n", jtag_delay);

   // Validate GPIO pins
   if (tck_gpio < 0 || tms_gpio < 0 || tdi_gpio < 0 || tdo_gpio < 0) {
      fprintf(stderr, "Error: Invalid GPIO pin numbers\n");
      return 1;
   }
   
   if (verbose) {
      printf("GPIO Configuration:\n");
      printf("  TCK: GPIO%d\n", tck_gpio);
      printf("  TMS: GPIO%d\n", tms_gpio);
      printf("  TDI: GPIO%d\n", tdi_gpio);
      printf("  TDO: GPIO%d\n", tdo_gpio);
      printf("  Port: %d\n", port);
   }

   if (!bcm2835gpio_init()) {
      fprintf(stderr,"Failed in bcm2835gpio_init()\n");
      return -1;
   }

   // Set up signal handler for cleanup
   signal(SIGINT, signal_handler);
   signal(SIGTERM, signal_handler);

   s = socket(AF_INET, SOCK_STREAM, 0);

   if (s < 0) {
      perror("socket");
      bcm2835gpio_cleanup();
      return 1;
   }

   i = 1;
   setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &i, sizeof i);

   address.sin_addr.s_addr = INADDR_ANY;
   address.sin_port = htons(port);
   address.sin_family = AF_INET;

   if (bind(s, (struct sockaddr*) &address, sizeof(address)) < 0) {
      perror("bind");
      bcm2835gpio_cleanup();
      return 1;
   }

   if (listen(s, 0) < 0) {
      perror("listen");
      bcm2835gpio_cleanup();
      return 1;
   }

   if (verbose) {
      printf("XVC server listening on port %d\n", port);
      printf("Use Ctrl+C to stop the server\n");
   }

   fd_set conn;
   int maxfd = 0;

   FD_ZERO(&conn);
   FD_SET(s, &conn);

   maxfd = s;

   while (running) {
      fd_set read = conn, except = conn;
      int fd;
      
      // Use timeout so we can check running flag
      struct timeval timeout;
      timeout.tv_sec = 1;
      timeout.tv_usec = 0;

      if (select(maxfd + 1, &read, 0, &except, &timeout) < 0) {
         if (errno == EINTR) {
            // Interrupted by signal, continue loop
            continue;
         }
         perror("select");
         break;
      }

      for (fd = 0; fd <= maxfd; ++fd) {
         if (FD_ISSET(fd, &read)) {
            if (fd == s) {
               int newfd;
               socklen_t nsize = sizeof(address);

               newfd = accept(s, (struct sockaddr*) &address, &nsize);

               if (verbose)
                  printf("connection accepted - fd %d\n", newfd);
               if (newfd < 0) {
                  perror("accept");
               } else {
                 int flag = 1;
                 int optResult = setsockopt(newfd,
                                               IPPROTO_TCP,
                                               TCP_NODELAY,
                                               (char *)&flag,
                                               sizeof(int));
                 if (optResult < 0)
                    perror("TCP_NODELAY error");
                  if (newfd > maxfd) {
                     maxfd = newfd;
                  }
                  FD_SET(newfd, &conn);
               }
            }
            else {
               int result = handle_data(fd);
               if (result == -1) { // Check for signal to exit
                  // handle_data returned -1, indicating exit
                  goto cleanup_and_exit;
               }
               else if (result) {
                  if (verbose)
                     printf("connection closed - fd %d\n", fd);
                  close(fd);
                  FD_CLR(fd, &conn);
               }
            }
         }
         else if (FD_ISSET(fd, &except)) {
            if (verbose)
               printf("connection aborted - fd %d\n", fd);
            close(fd);
            FD_CLR(fd, &conn);
            if (fd == s)
               break;
         }
      }
   }
   
cleanup_and_exit:
   bcm2835gpio_cleanup();
   return 0;
}

/*
 * This work, "xvcpi_modern.c", is a derivative of "xvcpi.c" 
 * Updated for modern Raspberry Pi systems using libgpiod
 *
 * Original "xvcpi.c" is licensed under CC0 1.0 Universal
 * by Derek Mulcahy.
 */
