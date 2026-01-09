public class ComparisonInThree {

    public static int comparisonInThreeMethod(int[] a1, int[] a2, int[] a3) {

        int p1 = 0, p2 = 0, p3 = 0;

        while (p1 < a1.length && p2 < a2.length && p3 < a3.length) {
            if (a1[p1] == a2[p2] && a1[p1] == a3[p3])
                return a1[p1];

            else if (a1[p1] < a2[p2] && a1[p1] < a3[p3])
                p1++;

            else if (a2[p2] < a1[p1] && a2[p2] < a3[p3])
                p2++;

            else
                p3++;
        }

        return -1;
    }

    public static void main(String[] args) {

        int[] array1 = { 3, 5, 7, 8, 10, 12 };
        int[] array2 = { 2, 4, 6, 7, 11 };
        int[] array3 = { 1, 2, 3, 4, 5, 6, 7 };

        System.out.println(comparisonInThreeMethod(array1, array2, array3));
    }
}